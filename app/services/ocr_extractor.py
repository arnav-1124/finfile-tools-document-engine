import io
import os
import statistics

import pytesseract
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.utils.file_helpers import create_success_response, normalize_column_count

load_dotenv()

tesseract_cmd = os.getenv("TESSERACT_CMD")

if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def preprocess_image_variants(image):
    """
    Creates multiple lightweight preprocessing variants.
    Later we will add OpenCV deskew/thresholding, but this gives us
    a better baseline without heavy dependency issues.
    """
    rgb_image = image.convert("RGB")
    grayscale = ImageOps.grayscale(rgb_image)

    contrast = ImageEnhance.Contrast(grayscale).enhance(2.0)
    sharpened = contrast.filter(ImageFilter.SHARPEN)

    enlarged = sharpened
    width, height = sharpened.size

    if width < 1600:
        scale = 1600 / max(width, 1)
        enlarged = sharpened.resize(
            (int(width * scale), int(height * scale)),
            Image.Resampling.LANCZOS,
        )

    autocontrast = ImageOps.autocontrast(enlarged)

    return [
        {
            "name": "grayscale",
            "image": grayscale,
        },
        {
            "name": "contrast_sharpen",
            "image": sharpened,
        },
        {
            "name": "enlarged_autocontrast",
            "image": autocontrast,
        },
    ]


def extract_words_with_confidence(image, config):
    data = pytesseract.image_to_data(
        image,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    words = []
    confidences = []

    for index, text in enumerate(data.get("text", [])):
        clean_text = text.strip()

        if not clean_text:
            continue

        try:
            confidence = float(data["conf"][index])
        except (ValueError, TypeError):
            confidence = -1

        words.append(clean_text)

        if confidence >= 0:
            confidences.append(confidence)

    average_confidence = statistics.mean(confidences) if confidences else 0

    return words, average_confidence


def extract_text_lines(image, config):
    text = pytesseract.image_to_string(image, config=config)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def score_ocr_result(lines, words, average_confidence):
    line_score = min(len(lines), 20) * 2
    word_score = min(len(words), 80)
    confidence_score = average_confidence

    return line_score + word_score + confidence_score


def run_best_ocr(image):
    variants = preprocess_image_variants(image)

    configs = [
        {
            "name": "psm_6",
            "config": "--oem 3 --psm 6",
        },
        {
            "name": "psm_4",
            "config": "--oem 3 --psm 4",
        },
        {
            "name": "psm_11",
            "config": "--oem 3 --psm 11",
        },
    ]

    best_result = {
        "score": -1,
        "lines": [],
        "words": [],
        "averageConfidence": 0,
        "variant": None,
        "config": None,
    }

    for variant in variants:
        for config_item in configs:
            config = config_item["config"]

            try:
                words, average_confidence = extract_words_with_confidence(
                    variant["image"],
                    config,
                )
                lines = extract_text_lines(variant["image"], config)

                score = score_ocr_result(lines, words, average_confidence)

                if score > best_result["score"]:
                    best_result = {
                        "score": score,
                        "lines": lines,
                        "words": words,
                        "averageConfidence": average_confidence,
                        "variant": variant["name"],
                        "config": config_item["name"],
                    }
            except Exception:
                continue

    return best_result


def lines_to_rows(lines):
    return [[line] for line in lines]


def extract_image_text(file_payload, image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    best_result = run_best_ocr(image)

    rows = lines_to_rows(best_result["lines"])
    columns, normalized_rows = normalize_column_count(rows)

    confidence_decimal = round(best_result["averageConfidence"] / 100, 2)

    warnings = []

    if not normalized_rows:
        warnings.append(
            "No readable text was detected from this image. Try a clearer scan or higher contrast image."
        )

    if normalized_rows and confidence_decimal < 0.55:
        warnings.append(
            "OCR confidence is low. Please review the extracted text carefully."
        )

    warnings.append(
        f"OCR strategy used: {best_result['variant']} with {best_result['config']}."
    )

    return create_success_response(
        extraction_strategy="IMAGE_OCR_TEXT_LINES",
        columns=columns or ["Extracted text"],
        rows=normalized_rows,
        total_rows=len(normalized_rows),
        warnings=warnings,
        confidence={"overall": confidence_decimal if normalized_rows else 0.0},
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

def extract_pil_image_with_ocr(image, *, source_label="Page"):
    best_result = run_best_ocr(image)

    rows = []

    for line in best_result["lines"]:
        rows.append([source_label, line])

    confidence_decimal = round(best_result["averageConfidence"] / 100, 2)

    warnings = []

    if not rows:
        warnings.append(
            f"No readable text was detected from {source_label}."
        )

    if rows and confidence_decimal < 0.55:
        warnings.append(
            f"OCR confidence is low for {source_label}. Please review extracted text carefully."
        )

    warnings.append(
        f"OCR strategy for {source_label}: {best_result['variant']} with {best_result['config']}."
    )

    return {
        "rows": rows,
        "warnings": warnings,
        "confidence": confidence_decimal if rows else 0.0,
    }


def extract_image_with_ocr(file_payload, image_bytes):
    try:
        return extract_image_text(file_payload, image_bytes)
    except Exception as error:
        fallback = extract_image_metadata(file_payload, image_bytes)
        fallback["warnings"].append(f"OCR failed: {str(error)}")
        return fallback