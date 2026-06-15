import base64
import io
import zipfile

import fitz


MAX_PDF_TO_IMAGES_BYTES = 50 * 1024 * 1024
MAX_PDF_TO_IMAGES_PAGES = 100


def decode_base64_file(file_payload):
    content_base64 = file_payload.get("contentBase64")

    if not content_base64:
        raise ValueError("PDF file content is missing.")

    return base64.b64decode(content_base64)


def validate_pdf_to_images_payload(payload):
    files = payload.get("files") or []

    if not files:
        raise ValueError("PDF file is required.")

    file_payload = files[0]

    if file_payload.get("mimeType") != "application/pdf":
        raise ValueError("Only PDF files are supported for PDF to Images.")

    size_bytes = file_payload.get("sizeBytes") or 0

    if size_bytes > MAX_PDF_TO_IMAGES_BYTES:
        raise ValueError("PDF to Images supports PDFs up to 50 MB.")

    return file_payload


def normalize_image_format(image_format):
    selected_format = str(image_format or "png").lower()

    if selected_format not in ["png", "jpg", "jpeg"]:
        raise ValueError("Image format must be png, jpg, or jpeg.")

    return "jpeg" if selected_format == "jpg" else selected_format


def convert_pdf_to_images(payload):
    file_payload = validate_pdf_to_images_payload(payload)
    image_format = normalize_image_format(payload.get("imageFormat"))

    pdf_bytes = decode_base64_file(file_payload)

    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = pdf_document.page_count

    if total_pages > MAX_PDF_TO_IMAGES_PAGES:
        raise ValueError(
            f"PDF to Images supports up to {MAX_PDF_TO_IMAGES_PAGES} pages for now."
        )

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for page_index in range(total_pages):
            page = pdf_document.load_page(page_index)

            matrix = fitz.Matrix(2, 2)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)

            page_number = page_index + 1

            if image_format == "jpeg":
                image_bytes = pixmap.tobytes("jpeg")
                filename = f"page-{page_number:03d}.jpg"
            else:
                image_bytes = pixmap.tobytes("png")
                filename = f"page-{page_number:03d}.png"

            zip_file.writestr(filename, image_bytes)

    pdf_document.close()

    zip_buffer.seek(0)

    zip_base64 = base64.b64encode(zip_buffer.read()).decode("utf-8")

    return {
        "success": True,
        "engineVersion": "0.1.0",
        "contentBase64": zip_base64,
        "filename": "pdf-images.zip",
        "contentType": "application/zip",
        "metadata": {
            "sourceType": "pdf",
            "outputFormat": image_format,
            "totalPages": total_pages,
            "outputImages": total_pages,
            "originalName": file_payload.get("originalName"),
        },
        "warnings": [],
    }
