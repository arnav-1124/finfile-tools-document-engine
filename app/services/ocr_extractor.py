import io
import os

import pytesseract
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter

from app.utils.file_helpers import create_success_response, normalize_column_count

load_dotenv()

tesseract_cmd = os.getenv("TESSERACT_CMD")

if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def preprocess_image_for_ocr(image):
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def extract_lines_from_ocr_text(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [[line] for line in lines]


def extract_image_text(file_payload, image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    processed_image = preprocess_image_for_ocr(image)

    text = pytesseract.image_to_string(processed_image, config="--psm 6")
    rows = extract_lines_from_ocr_text(text)
    columns, normalized_rows = normalize_column_count(rows)

    warnings = []

    if not normalized_rows:
        warnings.append(
            "No readable text was detected from this image. Try a clearer scan or higher contrast image."
        )

    return create_success_response(
        extraction_strategy="IMAGE_OCR_TEXT_LINES",
        columns=columns or ["Extracted text"],
        rows=normalized_rows,
        total_rows=len(normalized_rows),
        warnings=warnings,
        confidence={"overall": 0.55 if normalized_rows else 0.0},
    )


def extract_image_metadata(file_payload, image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size

    rows = [
        ["Image received", file_payload.get("originalName", "Unknown file")],
        ["Image size", f"{width} x {height}px"],
        ["OCR status", "OCR fallback metadata response"],
    ]

    return create_success_response(
        extraction_strategy="IMAGE_METADATA_FALLBACK",
        columns=["Field", "Value"],
        rows=rows,
        total_rows=len(rows),
        warnings=["Image metadata fallback was used."],
        confidence={"overall": 0.2},
    )


def extract_image_with_ocr(file_payload, image_bytes):
    try:
        return extract_image_text(file_payload, image_bytes)
    except Exception as error:
        fallback = extract_image_metadata(file_payload, image_bytes)
        fallback["warnings"].append(f"OCR failed: {str(error)}")
        return fallback