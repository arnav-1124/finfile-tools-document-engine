import html
import json
import re
from collections import Counter


TABLE_REGEX = re.compile(
    r"<table\b.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

TAG_REGEX = re.compile(r"<[^>]+>")

MAX_TEXT_BLOCK_CHARS = 12000
MAX_TABLE_TEXT_CHARS = 18000
MAX_PLAIN_TEXT_CHARS = 60000
REPETITION_RATIO_THRESHOLD = 0.42
REPEATED_PHRASE_MIN_COUNT = 8


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


def get_word_tokens(text):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", str(text or "").lower())


def get_repetition_score(text):
    tokens = get_word_tokens(text)

    if len(tokens) < 80:
        return 0

    token_counts = Counter(tokens)
    repeated_token_total = sum(
        count for count in token_counts.values() if count >= 8
    )

    return repeated_token_total / max(len(tokens), 1)


def find_repeated_phrases(text, phrase_size=6):
    tokens = get_word_tokens(text)

    if len(tokens) < phrase_size * 4:
        return []

    phrases = [
        " ".join(tokens[index: index + phrase_size])
        for index in range(0, len(tokens) - phrase_size + 1)
    ]

    phrase_counts = Counter(phrases)

    return [
        {
            "phrase": phrase,
            "count": count,
        }
        for phrase, count in phrase_counts.most_common(5)
        if count >= REPEATED_PHRASE_MIN_COUNT
    ]


def looks_hallucinated_or_repeated(text):
    normalized = normalize_spaces(text)

    if not normalized:
        return {
            "isSuspicious": False,
            "reason": None,
            "repetitionScore": 0,
            "repeatedPhrases": [],
        }

    repetition_score = get_repetition_score(normalized)
    repeated_phrases = find_repeated_phrases(normalized)

    has_common_loop = bool(
        re.search(
            r"(size and size|provided to the company|the product are not provided|and the size)",
            normalized,
            flags=re.IGNORECASE,
        )
    )

    is_suspicious = (
        repetition_score >= REPETITION_RATIO_THRESHOLD
        or bool(repeated_phrases)
        or has_common_loop
    )

    reason = None

    if is_suspicious:
        if has_common_loop:
            reason = "Repeated OCR/model-generated phrase pattern detected."
        elif repeated_phrases:
            reason = "Repeated phrase loop detected."
        else:
            reason = "Unusually high repeated-word ratio detected."

    return {
        "isSuspicious": is_suspicious,
        "reason": reason,
        "repetitionScore": round(repetition_score, 4),
        "repeatedPhrases": repeated_phrases,
    }


def truncate_safely(text, max_chars):
    value = str(text or "")

    if len(value) <= max_chars:
        return value

    truncated = value[:max_chars].rstrip()

    last_break = max(
        truncated.rfind("\n\n"),
        truncated.rfind(". "),
        truncated.rfind("</tr>"),
    )

    if last_break > max_chars * 0.55:
        truncated = truncated[:last_break].rstrip()

    return truncated + "\n\n[Output trimmed because OCR returned an unusually long repeated block.]"


def sanitize_block_text(text, max_chars):
    value = clean_text(text)
    quality = looks_hallucinated_or_repeated(value)

    warnings = []

    if quality["isSuspicious"]:
        warnings.append(quality["reason"])

    if len(value) > max_chars:
        warnings.append(
            f"Block was trimmed from {len(value)} to {max_chars} characters."
        )
        value = truncate_safely(value, max_chars)

    return {
        "text": value,
        "warnings": [warning for warning in warnings if warning],
        "quality": quality,
    }


def sanitize_table_html(table_html):
    original_html = str(table_html or "").strip()
    table_text = strip_html(original_html)

    quality = looks_hallucinated_or_repeated(table_text)
    warnings = []

    if quality["isSuspicious"]:
        warnings.append(quality["reason"])

    if len(table_text) > MAX_TABLE_TEXT_CHARS:
        warnings.append(
            f"Table text was unusually large and was trimmed from {len(table_text)} characters."
        )

        safe_text = truncate_safely(table_text, MAX_TABLE_TEXT_CHARS)

        fallback_html = (
            "<table border='1' style='margin: auto; word-wrap: break-word;'>"
            "<tr><td>"
            + html.escape(safe_text).replace("\n", "<br />")
            + "</td></tr></table>"
        )

        return {
            "html": fallback_html,
            "text": safe_text,
            "warnings": warnings,
            "quality": quality,
            "wasTrimmed": True,
        }

    if quality["isSuspicious"]:
        safe_text = truncate_safely(table_text, min(
            len(table_text), MAX_TABLE_TEXT_CHARS))

        fallback_html = (
            "<table border='1' style='margin: auto; word-wrap: break-word;'>"
            "<tr><td>"
            + html.escape(safe_text).replace("\n", "<br />")
            + "</td></tr></table>"
        )

        return {
            "html": fallback_html,
            "text": safe_text,
            "warnings": warnings,
            "quality": quality,
            "wasTrimmed": False,
        }

    return {
        "html": original_html,
        "text": table_text,
        "warnings": warnings,
        "quality": quality,
        "wasTrimmed": False,
    }


def extract_tables_from_markdown(markdown_text, page_number):
    tables = []

    for match in TABLE_REGEX.finditer(markdown_text or ""):
        table_html = match.group(0).strip()
        sanitized = sanitize_table_html(table_html)

        tables.append(
            {
                "pageNumber": page_number,
                "tableIndex": len(tables) + 1,
                "type": "table",
                "html": sanitized["html"],
                "markdown": sanitized["html"],
                "text": sanitized["text"],
                "bbox": None,
                "warnings": sanitized["warnings"],
                "quality": sanitized["quality"],
                "wasTrimmed": sanitized["wasTrimmed"],
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
            sanitized = sanitize_block_text(clean_before, MAX_TEXT_BLOCK_CHARS)

            blocks.append(
                {
                    "type": "text",
                    "pageNumber": page_number,
                    "text": sanitized["text"],
                    "markdown": sanitized["text"],
                    "bbox": None,
                    "warnings": sanitized["warnings"],
                    "quality": sanitized["quality"],
                }
            )

        table_index += 1
        table_html = match.group(0).strip()
        sanitized_table = sanitize_table_html(table_html)

        blocks.append(
            {
                "type": "table",
                "pageNumber": page_number,
                "tableIndex": table_index,
                "html": sanitized_table["html"],
                "markdown": sanitized_table["html"],
                "text": sanitized_table["text"],
                "bbox": None,
                "warnings": sanitized_table["warnings"],
                "quality": sanitized_table["quality"],
                "wasTrimmed": sanitized_table["wasTrimmed"],
            }
        )

        cursor = match.end()

    after = clean_text(markdown_text[cursor:])

    if after:
        clean_after = strip_html(after)
        sanitized = sanitize_block_text(clean_after, MAX_TEXT_BLOCK_CHARS)

        blocks.append(
            {
                "type": "text",
                "pageNumber": page_number,
                "text": sanitized["text"],
                "markdown": sanitized["text"],
                "bbox": None,
                "warnings": sanitized["warnings"],
                "quality": sanitized["quality"],
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


def is_block_quarantined(block):
    quality = block.get("quality") or {}

    return bool(quality.get("isSuspicious")) and len(block.get("text") or "") > 4000


def build_plain_text(blocks):
    parts = []

    for block in blocks:
        if is_block_quarantined(block):
            parts.append(
                f"[Page {block.get('pageNumber')}: Suspicious repeated OCR block was hidden from plain text output.]"
            )
            continue

        text = block.get("text") or ""

        if text:
            parts.append(text)

    plain_text = clean_text("\n\n".join(parts))

    if len(plain_text) > MAX_PLAIN_TEXT_CHARS:
        plain_text = truncate_safely(plain_text, MAX_PLAIN_TEXT_CHARS)

    return plain_text


def build_markdown(blocks):
    parts = []

    for block in blocks:
        if is_block_quarantined(block):
            parts.append(
                f"> Page {block.get('pageNumber')}: Suspicious repeated OCR block was hidden from Markdown output."
            )
            continue

        markdown = block.get("markdown") or block.get("text") or ""

        if markdown:
            parts.append(markdown)

    markdown = clean_text("\n\n---\n\n".join(parts))

    if len(markdown) > MAX_PLAIN_TEXT_CHARS:
        markdown = truncate_safely(markdown, MAX_PLAIN_TEXT_CHARS)

    return markdown


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

    quarantined_blocks = [
        {
            "pageNumber": block.get("pageNumber"),
            "type": block.get("type"),
            "tableIndex": block.get("tableIndex"),
            "reason": (block.get("quality") or {}).get("reason"),
            "textLength": len(block.get("text") or ""),
        }
        for block in normalized_blocks
        if is_block_quarantined(block)
    ]

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
            "quarantinedBlockCount": len(quarantined_blocks),
            "quarantinedBlocks": quarantined_blocks,
            "provider": "paddleocr_api",
            "rawPreviewOnly": True,
            "rawPreviewDisabled": True,
        },
    }
