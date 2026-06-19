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

    # NumPy arrays
    if hasattr(value, "tolist"):
        try:
            return safe_jsonable(value.tolist())
        except Exception:
            return str(value)

    # NumPy scalar values: np.int16, np.int64, np.float32, etc.
    if hasattr(value, "item"):
        try:
            return safe_jsonable(value.item())
        except Exception:
            return str(value)

    if isinstance(value, dict):
        safe_dict = {}

        for key, item in value.items():
            safe_key = str(safe_jsonable(key))
            safe_dict[safe_key] = safe_jsonable(item)

        return safe_dict

    if isinstance(value, (list, tuple, set)):
        return [safe_jsonable(item) for item in value]

    # PaddleOCR/PaddleX result objects sometimes expose useful dict methods.
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


def extract_html_from_result_item(item):
    if not isinstance(item, dict):
        return ""

    for key in [
        "html",
        "table_html",
        "pred_html",
        "rec_html",
        "table_html_pred",
    ]:
        value = item.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def extract_text_from_result_item(item):
    if not isinstance(item, dict):
        return ""

    for key in [
        "text",
        "content",
        "rec_text",
        "ocr_text",
        "table_text",
    ]:
        value = item.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def is_table_like_item(item):
    if not isinstance(item, dict):
        return False

    candidate_type = str(
        item.get("type")
        or item.get("label")
        or item.get("category")
        or item.get("block_type")
        or item.get("layout_type")
        or item.get("sub_label")
        or ""
    ).lower()

    if "table" in candidate_type:
        return True

    if extract_html_from_result_item(item):
        return True

    markdown = extract_markdown_from_result_item(item)

    if markdown and "|" in markdown:
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


def find_tables_in_value(value, page_number=1, tables=None):
    if tables is None:
        tables = []

    if isinstance(value, dict):
        current_page_number = (
            value.get("pageNumber")
            or value.get("page_number")
            or value.get("page_id")
            or page_number
        )

        if is_table_like_item(value):
            tables.append(
                {
                    "pageNumber": current_page_number,
                    "tableIndex": len(tables) + 1,
                    "type": str(
                        value.get("type")
                        or value.get("label")
                        or value.get("category")
                        or value.get("block_type")
                        or value.get("layout_type")
                        or "table"
                    ),
                    "html": extract_html_from_result_item(value),
                    "markdown": extract_markdown_from_result_item(value),
                    "text": extract_text_from_result_item(value),
                    "bbox": safe_jsonable(
                        value.get("bbox")
                        or value.get("box")
                        or value.get("poly")
                        or value.get("coordinate")
                    ),
                    "raw": None,
                }
            )

        for item in value.values():
            find_tables_in_value(
                item,
                page_number=current_page_number,
                tables=tables,
            )

    elif isinstance(value, list):
        for item in value:
            find_tables_in_value(item, page_number=page_number, tables=tables)

    return tables


def flatten_text_from_value(value, text_parts=None):
    if text_parts is None:
        text_parts = []

    if isinstance(value, dict):
        text = extract_text_from_result_item(value)

        if text:
            text_parts.append(text)

        markdown = extract_markdown_from_result_item(value)

        if markdown:
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

    tables = find_tables_in_value(json_result)

    markdown_parts = dedupe_strings(flatten_text_from_value(json_result))
    table_markdown_parts = [
        table.get("markdown")
        for table in tables
        if table.get("markdown")
    ]

    combined_markdown_parts = dedupe_strings(
        markdown_parts + table_markdown_parts
    )

    markdown = "\n\n".join(combined_markdown_parts).strip()
    plain_text = markdown

    return {
        "plainText": plain_text,
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
