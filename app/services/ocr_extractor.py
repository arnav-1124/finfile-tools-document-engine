import io

from PIL import Image

from app.utils.file_helpers import create_success_response


def extract_image_metadata(file_payload, image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size

    rows = [
        ["Image received", file_payload.get("originalName", "Unknown file")],
        ["Image size", f"{width} x {height}px"],
        ["OCR status", "Image OCR will be connected in the next engine phase"],
    ]

    return create_success_response(
        extraction_strategy="IMAGE_METADATA_OCR_PENDING",
        columns=["Field", "Value"],
        rows=rows,
        total_rows=len(rows),
        warnings=[
            "Image OCR is not connected yet. This confirms the Python document-engine bridge is working."
        ],
        confidence={"overall": 0.2},
    )