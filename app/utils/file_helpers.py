import base64


ENGINE_VERSION = "0.1.0"
DEFAULT_PREVIEW_LIMIT = 25


def decode_base64_file(file_payload):
    encoded_content = file_payload.get("contentBase64", "")

    if not encoded_content:
        raise ValueError("Missing file content.")

    return base64.b64decode(encoded_content)


def normalize_rows(rows):
    normalized_rows = []

    for row in rows:
        clean_row = []

        for cell in row:
            value = "" if cell is None else str(cell).strip()
            clean_row.append(value)

        if any(clean_row):
            normalized_rows.append(clean_row)

    return normalized_rows


def normalize_column_count(rows):
    if not rows:
        return [], []

    max_columns = max(len(row) for row in rows)

    normalized_rows = []
    for row in rows:
        normalized_rows.append(row + [""] * (max_columns - len(row)))

    columns = [f"Column {index + 1}" for index in range(max_columns)]

    return columns, normalized_rows


def create_success_response(
    *,
    extraction_strategy,
    columns,
    rows,
    total_rows=None,
    preview_limit=DEFAULT_PREVIEW_LIMIT,
    warnings=None,
    files_processed=1,
    confidence=None,
):
    return {
        "success": True,
        "engineVersion": ENGINE_VERSION,
        "extractionStrategy": extraction_strategy,
        "columns": columns,
        "rows": rows[:preview_limit],
        "totalRows": total_rows if total_rows is not None else len(rows),
        "previewLimit": preview_limit,
        "warnings": warnings or [],
        "filesProcessed": files_processed,
        "confidence": confidence or {"overall": None},
    }


def create_error_response(message, *, code="DOCUMENT_ENGINE_ERROR"):
    return {
        "success": False,
        "engineVersion": ENGINE_VERSION,
        "code": code,
        "message": message,
    }