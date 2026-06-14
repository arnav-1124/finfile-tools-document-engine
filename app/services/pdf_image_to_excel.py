from app.services.ocr_extractor import extract_image_with_ocr, extract_pil_image_with_ocr
from app.services.pdf_table_extractor import (
    extract_tables_with_pymupdf,
    extract_text_lines_from_pdf,
    render_pdf_pages_to_images,
)
import time

from app.utils.file_helpers import (
    DEFAULT_PREVIEW_LIMIT,
    create_success_response,
    decode_base64_file,
    get_elapsed_ms,
    normalize_column_count,
)


def extract_from_pdf(file_payload):
    file_start_time = time.perf_counter()
    pdf_bytes = decode_base64_file(file_payload)

    table_start_time = time.perf_counter()
    table_rows, table_warnings = extract_tables_with_pymupdf(pdf_bytes)
    table_extract_ms = get_elapsed_ms(table_start_time)

    if table_rows:
        columns, rows = normalize_column_count(table_rows)

        return create_success_response(
            extraction_strategy="DIGITAL_PDF_TABLE",
            columns=columns,
            rows=rows,
            total_rows=len(rows),
            preview_limit=DEFAULT_PREVIEW_LIMIT,
            warnings=table_warnings,
            confidence={
                "text": 0.9,
                "tableStructure": 0.82,
                "overall": 0.82,
            },
            metadata={
                "sourceType": "digital_pdf",
                "pagesProcessed": None,
                "pageLimitApplied": False,
            },
            performance={
                "fileMs": get_elapsed_ms(file_start_time),
                "digitalTableExtractMs": table_extract_ms,
            },
        )

    text_start_time = time.perf_counter()
    text_rows, text_warnings = extract_text_lines_from_pdf(pdf_bytes)
    text_extract_ms = get_elapsed_ms(text_start_time)

    if text_rows:
        columns, rows = normalize_column_count(text_rows)

        return create_success_response(
            extraction_strategy="DIGITAL_PDF_TEXT_LINES",
            columns=columns or ["Page", "Extracted text"],
            rows=rows,
            total_rows=len(rows),
            preview_limit=DEFAULT_PREVIEW_LIMIT,
            warnings=table_warnings + text_warnings,
            confidence={
                "text": 0.75,
                "tableStructure": 0.25,
                "overall": 0.5,
            },
            metadata={
                "sourceType": "digital_pdf",
                "pagesProcessed": None,
                "pageLimitApplied": False,
            },
            performance={
                "fileMs": get_elapsed_ms(file_start_time),
                "digitalTableExtractMs": table_extract_ms,
                "digitalTextExtractMs": text_extract_ms,
            },
        )

    render_start_time = time.perf_counter()

    rendered_pages, render_warnings = render_pdf_pages_to_images(
        pdf_bytes,
        max_pages=2,
        zoom=1.5,
    )

    render_ms = get_elapsed_ms(render_start_time)

    scanned_rows = []
    scanned_warnings = []
    confidences = []
    table_like_pages = 0
    page_performance = []

    for page in rendered_pages:
        page_start_time = time.perf_counter()

        result = extract_pil_image_with_ocr(
            page["image"],
            source_label=f"Page {page['pageNumber']}",
        )

        page_ms = get_elapsed_ms(page_start_time)

        scanned_rows.extend(result["rows"])
        scanned_warnings.extend(result["warnings"])

        if result["confidence"]:
            confidences.append(result["confidence"])

        if result.get("isTableLike"):
            table_like_pages += 1

        page_performance.append(
            {
                "pageNumber": page["pageNumber"],
                "ocrMs": page_ms,
                "isTableLike": result.get("isTableLike", False),
                "confidence": result.get("confidence", 0),
            }
        )

    columns, rows = normalize_column_count(scanned_rows)

    average_confidence = (
        round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    )

    table_structure_confidence = 0.65 if table_like_pages > 0 else 0.25

    return create_success_response(
        extraction_strategy=(
            "SCANNED_PDF_OCR_TABLE_RECONSTRUCTED"
            if table_like_pages > 0
            else "SCANNED_PDF_OCR_TEXT_LINES"
        ),
        columns=columns or ["Page", "Extracted text"],
        rows=rows,
        total_rows=len(rows),
        preview_limit=DEFAULT_PREVIEW_LIMIT,
        warnings=table_warnings + text_warnings + render_warnings + scanned_warnings,
        confidence={
            "text": average_confidence,
            "tableStructure": table_structure_confidence,
            "overall": round(
                (average_confidence * 0.65)
                + (table_structure_confidence * 0.35),
                2,
            ),
        },
        metadata={
            "sourceType": "scanned_pdf",
            "pagesProcessed": len(rendered_pages),
            "pageLimitApplied": len(rendered_pages) >= 2,
            "tableLikePages": table_like_pages,
        },
        performance={
            "fileMs": get_elapsed_ms(file_start_time),
            "digitalTableExtractMs": table_extract_ms,
            "digitalTextExtractMs": text_extract_ms,
            "renderMs": render_ms,
            "pagePerformance": page_performance,
        },
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
        metadata={
            "sourceType": "multi_file",
            "fileCount": len(results),
        },
        performance={
            "files": [
                result.get("performance", {})
                for result in results
            ],
        },
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
