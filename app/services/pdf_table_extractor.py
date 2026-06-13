import fitz

from app.utils.file_helpers import normalize_rows


def extract_tables_with_pymupdf(pdf_bytes):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_rows = []
    warnings = []

    for page_index, page in enumerate(document):
        try:
            tables = page.find_tables()

            if not tables or not tables.tables:
                continue

            for table in tables.tables:
                extracted_table = table.extract()
                table_rows = normalize_rows(extracted_table)

                if table_rows:
                    all_rows.extend(table_rows)

        except Exception as error:
            warnings.append(
                f"Table extraction skipped on page {page_index + 1}: {str(error)}"
            )

    document.close()

    return all_rows, warnings


def extract_text_lines_from_pdf(pdf_bytes):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    rows = []
    warnings = []

    for page_index, page in enumerate(document):
        text = page.get_text("text") or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for line in lines:
            rows.append([f"Page {page_index + 1}", line])

    document.close()

    if rows:
        warnings.append(
            "No clear table structure found. Returning extracted text lines as preview rows."
        )
    else:
        warnings.append(
            "No embedded text was found. This may be a scanned PDF and will require OCR."
        )

    return rows, warnings