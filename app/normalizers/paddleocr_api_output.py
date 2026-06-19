import html
import json
import re


TABLE_REGEX = re.compile(
    r"<table\b.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


def clean_text(value):
    return re.sub(r"\n{3,}", "\n\n", str(value or "").strip())


def strip_html(value):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_tables_from_markdown(markdown_text, page_number):
    tables = []

    for match in TABLE_REGEX.finditer(markdown_text or ""):
        table_html = match.group(0).strip()

        tables.append(
            {
                "pageNumber": page_number,
                "tableIndex": len(tables) + 1,
                "type": "table",
                "html": table_html,
                "markdown": table_html,
                "text": strip_html(table_html),
                "bbox": None,
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
            blocks.append(
                {
                    "type": "text",
                    "pageNumber": page_number,
                    "text": strip_html(before),
                    "markdown": before,
                    "bbox": None,
                }
            )

        table_index += 1
        table_html = match.group(0).strip()

        blocks.append(
            {
                "type": "table",
                "pageNumber": page_number,
                "tableIndex": table_index,
                "html": table_html,
                "markdown": table_html,
                "text": strip_html(table_html),
                "bbox": None,
            }
        )

        cursor = match.end()

    after = clean_text(markdown_text[cursor:])

    if after:
        blocks.append(
            {
                "type": "text",
                "pageNumber": page_number,
                "text": strip_html(after),
                "markdown": after,
                "bbox": None,
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
        if block.get("type") == "text":
            text = block.get("text") or ""

            if text:
                parts.append(text)

        elif block.get("type") == "table":
            text = block.get("text") or ""

            if text:
                parts.append(text)

    return clean_text("\n\n".join(parts))


def parse_jsonl_lines(jsonl_text):
    parsed_items = []

    for line in (jsonl_text or "").splitlines():
        line = line.strip()

        if not line:
            continue

        parsed_items.append(json.loads(line))

    return parsed_items


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

            pages.append(
                {
                    "pageNumber": page_number,
                    "markdownLength": len(markdown_text),
                    "tableCount": len(page_tables),
                    "imageCount": len(markdown.get("images") or {}),
                    "outputImageCount": len(layout_result.get("outputImages") or {}),
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

    markdown = clean_text(
        "\n\n---\n\n".join(
            block.get("markdown") or block.get("text") or ""
            for block in normalized_blocks
            if block.get("markdown") or block.get("text")
        )
    )

    plain_text = build_plain_text(normalized_blocks)

    return {
        "pageCount": page_number,
        "plainText": plain_text,
        "structuredContent": normalized_blocks,
        "documentBlocks": normalized_blocks,
        "tables": tables,
        "markdown": markdown,
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
            "provider": "paddleocr_api",
            "rawPreviewOnly": True,
            "rawPreviewDisabled": True,
        },
    }
