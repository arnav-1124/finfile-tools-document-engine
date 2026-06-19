import json
import math
import re
from pathlib import Path


def safe_jsonable(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, str):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")

    if hasattr(value, "tolist"):
        try:
            return safe_jsonable(value.tolist())
        except Exception:
            return str(value)

    if hasattr(value, "item"):
        try:
            return safe_jsonable(value.item())
        except Exception:
            return str(value)

    if isinstance(value, dict):
        return {
            str(safe_jsonable(key)): safe_jsonable(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [safe_jsonable(item) for item in value]

    if hasattr(value, "dict"):
        try:
            return safe_jsonable(value.dict())
        except Exception:
            pass

    if hasattr(value, "model_dump"):
        try:
            return safe_jsonable(value.model_dump())
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return safe_jsonable(vars(value))
        except Exception:
            pass

    try:
        json.dumps(value, allow_nan=False)
        return value
    except Exception:
        return str(value)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_html_table(value):
    return isinstance(value, str) and "<table" in value.lower()


def normalize_html_signature(html):
    html = str(html or "").lower()
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def extract_html_from_result_item(item):
    if not isinstance(item, dict):
        return ""

    for key in [
        "html",
        "table_html",
        "pred_html",
        "rec_html",
        "table_html_pred",
        "content",
        "text",
    ]:
        value = item.get(key)

        if is_html_table(value):
            return value.strip()

    return ""


def extract_markdown_from_result_item(item):
    if not isinstance(item, dict):
        return ""

    for key in [
        "markdown",
        "md",
        "markdown_text",
        "rec_markdown",
        "table_markdown",
    ]:
        value = item.get(key)

        if isinstance(value, str) and value.strip() and not is_html_table(value):
            return value.strip()

    return ""


def extract_text_from_result_item(item):
    if not isinstance(item, dict):
        return ""

    for key in ["text", "content", "rec_text", "ocr_text", "table_text"]:
        value = item.get(key)

        if isinstance(value, str) and value.strip() and not is_html_table(value):
            return value.strip()

    return ""


def get_bbox_from_item(item):
    if not isinstance(item, dict):
        return None

    return safe_jsonable(
        item.get("bbox")
        or item.get("box")
        or item.get("poly")
        or item.get("coordinate")
    )


def get_page_number_from_item(item, fallback_page_number=1):
    if not isinstance(item, dict):
        return fallback_page_number

    return (
        item.get("pageNumber")
        or item.get("page_number")
        or item.get("page_id")
        or fallback_page_number
    )


def get_label_from_item(item):
    if not isinstance(item, dict):
        return ""

    return str(
        item.get("type")
        or item.get("label")
        or item.get("category")
        or item.get("block_type")
        or item.get("layout_type")
        or item.get("sub_label")
        or ""
    ).lower()


def is_table_like_item(item):
    if not isinstance(item, dict):
        return False

    label = get_label_from_item(item)

    if "table" in label:
        return True

    if extract_html_from_result_item(item):
        return True

    table_keys = {
        "table",
        "tables",
        "table_res",
        "table_result",
        "table_structure",
        "cell_box_list",
        "table_cells",
        "pred_html",
        "rec_html",
    }

    return any(key in item for key in table_keys)


def is_text_like_item(item):
    if not isinstance(item, dict):
        return False

    if is_table_like_item(item):
        return False

    label = get_label_from_item(item)

    if any(token in label for token in ["text", "title", "paragraph", "header"]):
        return True

    return bool(extract_text_from_result_item(item) or extract_markdown_from_result_item(item))


def collect_table_candidates(value, page_number=1, candidates=None):
    if candidates is None:
        candidates = []

    if isinstance(value, dict):
        current_page_number = get_page_number_from_item(value, page_number)

        if is_table_like_item(value):
            html = extract_html_from_result_item(value)
            markdown = extract_markdown_from_result_item(value)
            text = extract_text_from_result_item(value)
            bbox = get_bbox_from_item(value)

            candidates.append(
                {
                    "pageNumber": current_page_number,
                    "type": "table",
                    "html": html,
                    "markdown": markdown,
                    "text": text,
                    "bbox": bbox,
                    "hasHtml": bool(html),
                    "hasText": bool(text),
                    "sourceLabel": get_label_from_item(value),
                }
            )

        for item in value.values():
            collect_table_candidates(
                item,
                page_number=current_page_number,
                candidates=candidates,
            )

    elif isinstance(value, list):
        for item in value:
            collect_table_candidates(
                item, page_number=page_number, candidates=candidates)

    return candidates


def collect_text_candidates(value, page_number=1, candidates=None):
    if candidates is None:
        candidates = []

    if isinstance(value, dict):
        current_page_number = get_page_number_from_item(value, page_number)

        if is_text_like_item(value):
            text = extract_text_from_result_item(
                value) or extract_markdown_from_result_item(value)
            text = clean_text(text)

            if text:
                candidates.append(
                    {
                        "pageNumber": current_page_number,
                        "type": "text",
                        "text": text,
                        "bbox": get_bbox_from_item(value),
                        "sourceLabel": get_label_from_item(value),
                    }
                )

        for item in value.values():
            collect_text_candidates(
                item,
                page_number=current_page_number,
                candidates=candidates,
            )

    elif isinstance(value, list):
        for item in value:
            collect_text_candidates(
                item, page_number=page_number, candidates=candidates)

    return candidates


def dedupe_tables(candidates):
    deduped = []
    seen_html = set()
    seen_bbox = set()

    html_candidates = [item for item in candidates if item.get("html")]

    for item in html_candidates:
        html_signature = normalize_html_signature(item.get("html"))

        if html_signature in seen_html:
            continue

        seen_html.add(html_signature)
        deduped.append(item)

    if not deduped:
        for item in candidates:
            bbox = item.get("bbox")
            bbox_signature = json.dumps(bbox, sort_keys=True) if bbox else ""

            if bbox_signature and bbox_signature in seen_bbox:
                continue

            if bbox_signature:
                seen_bbox.add(bbox_signature)

            if item.get("text") or item.get("bbox"):
                deduped.append(item)

    return [
        {
            "pageNumber": item.get("pageNumber") or 1,
            "tableIndex": index + 1,
            "type": "table",
            "html": item.get("html") or "",
            "markdown": item.get("markdown") or "",
            "text": item.get("text") or "",
            "bbox": item.get("bbox"),
        }
        for index, item in enumerate(deduped)
    ]


def dedupe_text_blocks(candidates):
    seen = set()
    deduped = []

    for item in candidates:
        text = clean_text(item.get("text"))

        if not text:
            continue

        if is_html_table(text):
            continue

        signature = text.lower()

        if signature in seen:
            continue

        seen.add(signature)

        deduped.append(
            {
                "pageNumber": item.get("pageNumber") or 1,
                "type": "text",
                "text": text,
                "bbox": item.get("bbox"),
            }
        )

    return deduped


def get_block_sort_key(block):
    bbox = block.get("bbox")

    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            return (
                int(block.get("pageNumber") or 1),
                float(bbox[1]),
                float(bbox[0]),
            )
        except Exception:
            pass

    return (
        int(block.get("pageNumber") or 1),
        10**9,
        10**9,
    )


def build_structured_content(text_blocks, tables):
    blocks = []

    for block in text_blocks:
        blocks.append(
            {
                "type": "text",
                "pageNumber": block.get("pageNumber") or 1,
                "text": block.get("text") or "",
                "bbox": block.get("bbox"),
            }
        )

    for table in tables:
        blocks.append(
            {
                "type": "table",
                "pageNumber": table.get("pageNumber") or 1,
                "tableIndex": table.get("tableIndex"),
                "html": table.get("html") or "",
                "markdown": table.get("markdown") or "",
                "text": table.get("text") or "",
                "bbox": table.get("bbox"),
            }
        )

    return sorted(blocks, key=get_block_sort_key)


def build_plain_text(text_blocks):
    return "\n\n".join(
        block["text"]
        for block in text_blocks
        if block.get("text")
    ).strip()


def build_markdown(text_blocks, tables, structured_content):
    markdown_parts = []

    for block in structured_content:
        if block["type"] == "text" and block.get("text"):
            markdown_parts.append(block["text"])

        if block["type"] == "table":
            if block.get("markdown"):
                markdown_parts.append(block["markdown"])
            elif block.get("html"):
                markdown_parts.append(block["html"])
            elif block.get("text"):
                markdown_parts.append(block["text"])

    seen = set()
    deduped = []

    for part in markdown_parts:
        clean_part = str(part or "").strip()

        if not clean_part:
            continue

        signature = clean_part.lower()

        if signature in seen:
            continue

        seen.add(signature)
        deduped.append(clean_part)

    return "\n\n".join(deduped).strip()


def normalize_document_parse_result(raw_result):
    json_result = safe_jsonable(raw_result)

    table_candidates = collect_table_candidates(json_result)
    text_candidates = collect_text_candidates(json_result)

    tables = dedupe_tables(table_candidates)
    text_blocks = dedupe_text_blocks(text_candidates)
    structured_content = build_structured_content(text_blocks, tables)

    plain_text = build_plain_text(text_blocks)
    markdown = build_markdown(text_blocks, tables, structured_content)

    return {
        "plainText": plain_text,
        "structuredContent": structured_content,
        "documentBlocks": structured_content,
        "tables": tables,
        "markdown": markdown,
        "json": {
            "pages": [],
            "blocks": structured_content,
            "tables": tables,
            "tableCount": len(tables),
            "textBlockCount": len(text_blocks),
            "rawPreviewOnly": True,
            "rawPreviewDisabled": True,
            "message": "Raw PPStructureV3 output is hidden because it is too large for normal API responses.",
        },
    }
