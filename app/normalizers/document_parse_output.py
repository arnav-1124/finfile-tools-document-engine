import json
import math
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
        return {str(safe_jsonable(key)): safe_jsonable(item) for key, item in value.items()}

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
    ]:
        value = item.get(key)

        if isinstance(value, str) and "<table" in value.lower():
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

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def extract_text_from_result_item(item):
    if not isinstance(item, dict):
        return ""

    for key in ["text", "content", "rec_text", "ocr_text", "table_text"]:
        value = item.get(key)

        if isinstance(value, str) and value.strip():
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


def is_table_layout_only(item):
    if not isinstance(item, dict):
        return False

    label = str(
        item.get("label")
        or item.get("type")
        or item.get("category")
        or item.get("block_type")
        or item.get("layout_type")
        or ""
    ).lower()

    has_table_label = "table" in label
    has_html = bool(extract_html_from_result_item(item))

    return has_table_label and not has_html


def is_table_like_item(item):
    if not isinstance(item, dict):
        return False

    label = str(
        item.get("type")
        or item.get("label")
        or item.get("category")
        or item.get("block_type")
        or item.get("layout_type")
        or item.get("sub_label")
        or ""
    ).lower()

    if "table" in label:
        return True

    if extract_html_from_result_item(item):
        return True

    markdown = extract_markdown_from_result_item(item)
    if markdown and "|" in markdown:
        return True

    return any(
        key in item
        for key in [
            "table",
            "tables",
            "table_res",
            "table_result",
            "table_structure",
            "cell_box_list",
            "table_cells",
            "pred_html",
            "rec_html",
        ]
    )


def collect_table_candidates(value, page_number=1, candidates=None):
    if candidates is None:
        candidates = []

    if isinstance(value, dict):
        current_page_number = get_page_number_from_item(value, page_number)

        if is_table_like_item(value):
            html = extract_html_from_result_item(value)
            markdown = extract_markdown_from_result_item(value)
            text = extract_text_from_result_item(value)

            candidates.append(
                {
                    "pageNumber": current_page_number,
                    "type": str(
                        value.get("type")
                        or value.get("label")
                        or value.get("category")
                        or value.get("block_type")
                        or value.get("layout_type")
                        or "table"
                    ),
                    "html": html,
                    "markdown": markdown,
                    "text": text if not html else "",
                    "bbox": get_bbox_from_item(value),
                    "hasHtml": bool(html),
                    "isLayoutOnly": is_table_layout_only(value),
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


def normalize_html_signature(html):
    return " ".join(str(html or "").lower().split())


def dedupe_tables(candidates):
    deduped = []
    seen_html = set()
    seen_bbox = set()

    html_candidates = [item for item in candidates if item.get("hasHtml")]

    for item in html_candidates:
        html_signature = normalize_html_signature(item.get("html"))

        if html_signature and html_signature in seen_html:
            continue

        if html_signature:
            seen_html.add(html_signature)

        deduped.append(item)

    if deduped:
        return [
            {
                "pageNumber": item["pageNumber"],
                "tableIndex": index + 1,
                "type": "table",
                "html": item.get("html") or "",
                "markdown": item.get("markdown") or "",
                "text": item.get("text") or "",
                "bbox": item.get("bbox"),
            }
            for index, item in enumerate(deduped)
        ]

    for item in candidates:
        if item.get("isLayoutOnly"):
            bbox_signature = json.dumps(item.get("bbox"), sort_keys=True)

            if bbox_signature in seen_bbox:
                continue

            seen_bbox.add(bbox_signature)
            deduped.append(item)

    return [
        {
            "pageNumber": item["pageNumber"],
            "tableIndex": index + 1,
            "type": "table",
            "html": item.get("html") or "",
            "markdown": item.get("markdown") or "",
            "text": item.get("text") or "",
            "bbox": item.get("bbox"),
        }
        for index, item in enumerate(deduped)
    ]


def flatten_text_from_value(value, text_parts=None):
    if text_parts is None:
        text_parts = []

    if isinstance(value, dict):
        text = extract_text_from_result_item(value)

        if text and "<table" not in text.lower():
            text_parts.append(text)

        markdown = extract_markdown_from_result_item(value)

        if markdown and "<table" not in markdown.lower():
            text_parts.append(markdown)

        for item in value.values():
            flatten_text_from_value(item, text_parts=text_parts)

    elif isinstance(value, list):
        for item in value:
            flatten_text_from_value(item, text_parts=text_parts)

    return text_parts


def dedupe_strings(items):
    seen = set()
    deduped = []

    for item in items:
        clean_item = str(item or "").strip()

        if not clean_item:
            continue

        if clean_item in seen:
            continue

        seen.add(clean_item)
        deduped.append(clean_item)

    return deduped


def normalize_document_parse_result(raw_result):
    json_result = safe_jsonable(raw_result)

    table_candidates = collect_table_candidates(json_result)
    tables = dedupe_tables(table_candidates)

    text_parts = dedupe_strings(flatten_text_from_value(json_result))

    table_html_parts = [
        table["html"]
        for table in tables
        if table.get("html")
    ]

    markdown = "\n\n".join(dedupe_strings(
        text_parts + table_html_parts)).strip()

    return {
        "plainText": "\n\n".join(text_parts).strip(),
        "markdown": markdown,
        "tables": tables,
        "json": {
            "tables": tables,
            "tableCount": len(tables),
            "rawPreviewOnly": True,
            "rawPreviewDisabled": True,
            "message": "Raw PPStructureV3 output is hidden because it is too large for normal API responses.",
        },
    }
