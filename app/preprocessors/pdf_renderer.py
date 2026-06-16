import tempfile
from pathlib import Path

import fitz


def render_pdf_pages_to_images(pdf_bytes, scale=2):
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)

    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    image_paths = []

    try:
        for page_index in range(pdf_document.page_count):
            page = pdf_document.load_page(page_index)
            matrix = fitz.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)

            image_path = temp_path / f"page-{page_index + 1:03d}.png"
            pixmap.save(str(image_path))

            image_paths.append(
                {
                    "pageNumber": page_index + 1,
                    "imagePath": str(image_path),
                }
            )

        return {
            "tempDir": temp_dir,
            "pageCount": pdf_document.page_count,
            "pages": image_paths,
        }

    finally:
        pdf_document.close()
