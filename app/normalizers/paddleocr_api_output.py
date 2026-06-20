import html
import json
import re
from collections import Counter


TABLE_REGEX = re.compile(
    r"<table\b.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

TAG_REGEX = re.compile(r"<[^>]+>")


def clean_text(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_spaces(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_html(value):
    text = TAG_REGEX.sub(" ", str(value or ""))
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_jsonl_lines(jsonl_text):
    parsed_items = []

    for line in (jsonl_text or "").splitlines():
        line = line.strip()

        if not line:
            continue

        parsed_items.append(json.loads(line))

    return parsed_items


def create_text_block(text):
    value = strip_html(clean_text(text))

    return {
        "text": value,
        "warnings": [],
    }


def create_table_block(table_html):
    html_value = str(table_html or "").strip()

    return {
        "html": html_value,
        "text": strip_html(html_value),
        "warnings": [],
    }


def extract_tables_from_markdown(markdown_text, page_number):
    tables = []

    for match in TABLE_REGEX.finditer(markdown_text or ""):
        table_html = match.group(0).strip()
        table_data = create_table_block(table_html)

        tables.append(
            {
                "pageNumber": page_number,
                "tableIndex": len(tables) + 1,
                "type": "table",
                "html": table_data["html"],
                "markdown": table_data["html"],
                "text": table_data["text"],
                "bbox": None,
                "warnings": [],
            }
        )

    return tables


def split_markdown_into_blocks(markdown_text, page_number, table_index_offset=0):
    blocks = []
    cursor = 0
    table_index = table_index_offset

    for match in TABLE_REGEX.finditer(markdown_text or ""):
        before = clean_text(markdown_text[cursor:match.start()])

        if before:
            clean_before = strip_html(before)
            block_data = create_text_block(clean_before)

            blocks.append(
                {
                    "type": "text",
                    "pageNumber": page_number,
                    "text": block_data["text"],
                    "markdown": block_data["text"],
                    "bbox": None,
                    "warnings": [],
                }
            )

        table_index += 1
        table_html = match.group(0).strip()
        table_data = create_table_block(table_html)

        blocks.append(
            {
                "type": "table",
                "pageNumber": page_number,
                "tableIndex": table_index,
                "html": table_data["html"],
                "markdown": table_data["html"],
                "text": table_data["text"],
                "bbox": None,
                "warnings": [],
            }
        )

        cursor = match.end()

    cursor = max(cursor, 0)

    after = clean_text(markdown_text[cursor:])

    if after:
        clean_after = strip_html(after)
        block_data = create_text_block(clean_after)

        blocks.append(
            {
                "type": "text",
                "pageNumber": page_number,
                "text": block_data["text"],
                "markdown": block_data["text"],
                "bbox": None,
                "warnings": [],
            }
        )

    return blocks


def dedupe_tables(tables):
    seen = set()
    deduped = []

    for table in tables:
        signature = re.sub(r"\s+", " ", table.get("html", "").lower()).strip()

        if not signature:
            continue

        if signature in seen:
            continue

        seen.add(signature)

        clean_table = {
            **table,
            "tableIndex": len(deduped) + 1,
        }

        deduped.append(clean_table)

    return deduped


def build_plain_text(blocks):
    parts = []

    for block in blocks:
        text = block.get("text") or ""

        if text:
            parts.append(text)

    return clean_text("\n\n".join(parts))


def build_markdown(blocks):
    parts = []

    for block in blocks:
        markdown = block.get("markdown") or block.get("text") or ""

        if markdown:
            parts.append(markdown)

    return clean_text("\n\n---\n\n".join(parts))


def collect_warnings(blocks, pages):
    warnings = []

    for page in pages:
        if page.get("tableCount") == 0:
            warnings.append(
                {
                    "pageNumber": page.get("pageNumber"),
                    "type": "NO_TABLES_DETECTED",
                    "message": "No structured table was detected on this page.",
                }
            )

    for block in blocks:
        for warning in block.get("warnings") or []:
            warnings.append(
                {
                    "pageNumber": block.get("pageNumber"),
                    "type": "OCR_QUALITY_WARNING",
                    "message": warning,
                    "blockType": block.get("type"),
                    "tableIndex": block.get("tableIndex"),
                }
            )

    return warnings


def normalize_paddleocr_api_jsonl(jsonl_text):
    parsed_items = parse_jsonl_lines(jsonl_text)

    all_blocks = []
    all_tables = []
    pages = []

    page_number = 0
    table_index_offset = 0

    for item in parsed_items:
        result = item.get("result") or {}
        layout_results = result.get("layoutParsingResults") or []

        for layout_result in layout_results:
            page_number += 1

            markdown = layout_result.get("markdown") or {}
            markdown_text = markdown.get("text") or ""

            page_tables = extract_tables_from_markdown(
                markdown_text,
                page_number=page_number,
            )

            page_blocks = split_markdown_into_blocks(
                markdown_text,
                page_number=page_number,
                table_index_offset=table_index_offset,
            )

            table_index_offset += len(page_tables)

            all_tables.extend(page_tables)
            all_blocks.extend(page_blocks)

            page_warning_count = sum(
                len(block.get("warnings") or [])
                for block in page_blocks
            )

            pages.append(
                {
                    "pageNumber": page_number,
                    "markdownLength": len(markdown_text),
                    "tableCount": len(page_tables),
                    "imageCount": len(markdown.get("images") or {}),
                    "outputImageCount": len(layout_result.get("outputImages") or {}),
                    "warningCount": page_warning_count,
                }
            )

    tables = dedupe_tables(all_tables)

    normalized_blocks = []
    table_counter = 0

    for block in all_blocks:
        if block.get("type") == "table":
            table_counter += 1
            block = {
                **block,
                "tableIndex": table_counter,
            }

        normalized_blocks.append(block)

    plain_text = build_plain_text(normalized_blocks)
    markdown = build_markdown(normalized_blocks)
    warnings = collect_warnings(normalized_blocks, pages)

    return {
        "pageCount": page_number,
        "plainText": plain_text,
        "structuredContent": normalized_blocks,
        "documentBlocks": normalized_blocks,
        "tables": tables,
        "markdown": markdown,
        "warnings": warnings,
        "json": {
            "pages": pages,
            "blocks": normalized_blocks,
            "tables": tables,
            "tableCount": len(tables),
            "textBlockCount": len(
                [
                    block
                    for block in normalized_blocks
                    if block.get("type") == "text"
                ]
            ),
            "warningCount": len(warnings),
            "provider": "paddleocr_api",
            "rawPreviewOnly": True,
            "rawPreviewDisabled": True,
        },
    }
