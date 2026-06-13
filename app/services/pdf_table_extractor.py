import io

import fitz
from PIL import Image

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


def render_pdf_pages_to_images(pdf_bytes, *, max_pages=5, zoom=2):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    warnings = []

    page_count = len(document)
    pages_to_render = min(page_count, max_pages)

    if page_count > max_pages:
        warnings.append(
            f"Only the first {max_pages} pages were rendered for OCR preview. Full scanned-PDF processing will be expanded later."
        )

    matrix = fitz.Matrix(zoom, zoom)

    for page_index in range(pages_to_render):
        page = document[page_index]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        image_bytes = pixmap.tobytes("png")
        image = Image.open(io.BytesIO(image_bytes))

        images.append(
            {
                "pageNumber": page_index + 1,
                "image": image,
            }
        )

    document.close()

    return images, warnings