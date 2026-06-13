from app.services.ocr_extractor import extract_image_with_ocr, extract_pil_image_with_ocr
from app.services.pdf_table_extractor import (
    extract_tables_with_pymupdf,
    extract_text_lines_from_pdf,
    render_pdf_pages_to_images,
)
from app.utils.file_helpers import (
    DEFAULT_PREVIEW_LIMIT,
    create_success_response,
    decode_base64_file,
    normalize_column_count,
)

def extract_from_pdf(file_payload):
    pdf_bytes = decode_base64_file(file_payload)

    table_rows, table_warnings = extract_tables_with_pymupdf(pdf_bytes)

    if table_rows:
        columns, rows = normalize_column_count(table_rows)

        return create_success_response(
            extraction_strategy="DIGITAL_PDF_TABLE",
            columns=columns,
            rows=rows,
            total_rows=len(rows),
            preview_limit=DEFAULT_PREVIEW_LIMIT,
            warnings=table_warnings,
            confidence={"overall": 0.82},
        )

    text_rows, text_warnings = extract_text_lines_from_pdf(pdf_bytes)

    if text_rows:
        columns, rows = normalize_column_count(text_rows)

        return create_success_response(
            extraction_strategy="DIGITAL_PDF_TEXT_LINES",
            columns=columns or ["Column 1"],
            rows=rows,
            total_rows=len(rows),
            preview_limit=DEFAULT_PREVIEW_LIMIT,
            warnings=table_warnings + text_warnings,
            confidence={"overall": 0.62},
        )

    rendered_pages, render_warnings = render_pdf_pages_to_images(
        pdf_bytes,
        max_pages=5,
        zoom=2,
    )

    scanned_rows = []
    scanned_warnings = []
    confidences = []

    for page in rendered_pages:
        result = extract_pil_image_with_ocr(
            page["image"],
            source_label=f"Page {page['pageNumber']}",
        )

        scanned_rows.extend(result["rows"])
        scanned_warnings.extend(result["warnings"])

        if result["confidence"]:
            confidences.append(result["confidence"])

    columns, rows = normalize_column_count(scanned_rows)

    average_confidence = (
        round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    )

    return create_success_response(
        extraction_strategy="SCANNED_PDF_OCR_TEXT_LINES",
        columns=columns or ["Page", "Extracted text"],
        rows=rows,
        total_rows=len(rows),
        preview_limit=DEFAULT_PREVIEW_LIMIT,
        warnings=table_warnings + text_warnings + render_warnings + scanned_warnings,
        confidence={"overall": average_confidence},
    )


def extract_from_image(file_payload):
    image_bytes = decode_base64_file(file_payload)

    return extract_image_with_ocr(file_payload, image_bytes)


def combine_results(results):
    if not results:
        return create_success_response(
            extraction_strategy="NO_RESULT",
            columns=["Column 1"],
            rows=[],
            total_rows=0,
            preview_limit=DEFAULT_PREVIEW_LIMIT,
            warnings=["No files were processed."],
            files_processed=0,
            confidence={"overall": 0.0},
        )

    if len(results) == 1:
        return results[0]

    combined_rows = []
    warnings = []

    for index, result in enumerate(results):
        warnings.extend(result.get("warnings", []))

        file_label = f"File {index + 1}"

        for row in result.get("rows", []):
            combined_rows.append([file_label, *row])

    max_columns = max((len(row) for row in combined_rows), default=1)
    columns = ["Source file"] + [
        f"Column {index + 1}" for index in range(max_columns - 1)
    ]

    normalized_rows = []
    for row in combined_rows:
        normalized_rows.append(row + [""] * (max_columns - len(row)))

    return create_success_response(
        extraction_strategy="MULTI_FILE_COMBINED",
        columns=columns,
        rows=normalized_rows,
        total_rows=len(normalized_rows),
        preview_limit=DEFAULT_PREVIEW_LIMIT,
        warnings=warnings,
        files_processed=len(results),
        confidence={"overall": None},
    )


def extract_pdf_image_to_excel(payload):
    files = payload.get("files", [])
    results = []

    for file_payload in files:
        mime_type = file_payload.get("mimeType", "")

        if mime_type == "application/pdf":
            results.append(extract_from_pdf(file_payload))
            continue

        if mime_type in ["image/png", "image/jpeg"]:
            results.append(extract_from_image(file_payload))
            continue

        results.append(
            create_success_response(
                extraction_strategy="UNSUPPORTED_FILE_SKIPPED",
                columns=["File", "Status"],
                rows=[
                    [
                        file_payload.get("originalName", "Unknown file"),
                        f"Unsupported MIME type: {mime_type}",
                    ]
                ],
                total_rows=1,
                warnings=["Unsupported file type skipped."],
                confidence={"overall": 0.0},
            )
        )

    return combine_results(results)