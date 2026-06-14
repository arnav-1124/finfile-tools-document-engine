import io
import os
import statistics

import pytesseract
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.utils.file_helpers import create_success_response, normalize_column_count
from app.services.table_reconstructor import reconstruct_table_from_ocr_lines

from app.services.paddle_table_extractor import (
    extract_with_paddle_from_image_bytes,
    extract_with_paddle_from_pil_image,
)

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


def extract_image_text(file_payload, image_bytes):
    try:
        paddle_result = extract_with_paddle_from_image_bytes(image_bytes)

        if paddle_result["rows"]:
            strategy = (
                "IMAGE_PADDLE_TABLE_RECONSTRUCTED"
                if paddle_result["isTableLike"]
                else "IMAGE_PADDLE_TEXT_LINES"
            )

            warnings = paddle_result["warnings"]

            if paddle_result["confidence"] < 0.55:
                warnings.append(
                    "PaddleOCR confidence is low. Please review extracted text carefully."
                )

            return create_success_response(
                extraction_strategy=strategy,
                columns=paddle_result["columns"] or ["Extracted text"],
                rows=paddle_result["rows"],
                total_rows=len(paddle_result["rows"]),
                warnings=warnings,
                confidence={
                    "text": paddle_result["confidence"],
                    "tableStructure": 0.65 if paddle_result["isTableLike"] else 0.25,
                    "overall": round(
                        (paddle_result["confidence"] * 0.65)
                        + ((0.65 if paddle_result["isTableLike"] else 0.25) * 0.35),
                        2,
                    ),
                },
            )
    except Exception as error:
        paddle_error = str(error)
    else:
        paddle_error = "PaddleOCR returned no rows."

    image = Image.open(io.BytesIO(image_bytes))
    best_result = run_best_ocr(image)

    reconstruction = reconstruct_table_from_ocr_lines(best_result["lines"])

    columns = reconstruction["columns"]
    normalized_rows = reconstruction["rows"]

    confidence_decimal = round(best_result["averageConfidence"] / 100, 2)

    warnings = [
        f"PaddleOCR fallback reason: {paddle_error}",
    ]

    if not normalized_rows:
        warnings.append(
            "No readable text was detected from this image. Try a clearer scan or higher contrast image."
        )

    if normalized_rows and confidence_decimal < 0.55:
        warnings.append(
            "Tesseract OCR confidence is low. Please review the extracted text carefully."
        )

    warnings.append(
        f"Tesseract OCR strategy used: {best_result['variant']} with {best_result['config']}."
    )

    warnings.extend(reconstruction["warnings"])

    strategy = (
        "IMAGE_TESSERACT_TABLE_RECONSTRUCTED"
        if reconstruction["isTableLike"]
        else "IMAGE_TESSERACT_TEXT_LINES"
    )

    return create_success_response(
        extraction_strategy=strategy,
        columns=columns or ["Extracted text"],
        rows=normalized_rows,
        total_rows=len(normalized_rows),
        warnings=warnings,
        confidence={
            "text": confidence_decimal if normalized_rows else 0.0,
            "tableStructure": 0.65 if reconstruction["isTableLike"] else 0.25,
            "overall": round(
                ((confidence_decimal if normalized_rows else 0.0) * 0.65)
                + ((0.65 if reconstruction["isTableLike"] else 0.25) * 0.35),
                2,
            ),
        },
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
    try:
        paddle_result = extract_with_paddle_from_pil_image(image)

        if paddle_result["rows"]:
            rows = []

            if paddle_result["isTableLike"]:
                for row in paddle_result["rows"]:
                    rows.append([source_label, *row])
            else:
                for row in paddle_result["rows"]:
                    rows.append(
                        [source_label, *(row if isinstance(row, list) else [row])])

            warnings = [
                f"PaddleOCR strategy for {source_label}.",
                *paddle_result["warnings"],
            ]

            if paddle_result["confidence"] < 0.55:
                warnings.append(
                    f"PaddleOCR confidence is low for {source_label}. Please review extracted text carefully."
                )

            return {
                "rows": rows,
                "warnings": warnings,
                "confidence": paddle_result["confidence"],
                "isTableLike": paddle_result["isTableLike"],
            }

    except Exception as error:
        paddle_error = str(error)
    else:
        paddle_error = "PaddleOCR returned no rows."

    best_result = run_best_ocr(image)
    reconstruction = reconstruct_table_from_ocr_lines(best_result["lines"])

    rows = []

    if reconstruction["isTableLike"]:
        for row in reconstruction["rows"]:
            rows.append([source_label, *row])
    else:
        for line in best_result["lines"]:
            rows.append([source_label, line])

    confidence_decimal = round(best_result["averageConfidence"] / 100, 2)

    warnings = [
        f"PaddleOCR fallback reason for {source_label}: {paddle_error}",
    ]

    if not rows:
        warnings.append(f"No readable text was detected from {source_label}.")

    if rows and confidence_decimal < 0.55:
        warnings.append(
            f"Tesseract OCR confidence is low for {source_label}. Please review extracted text carefully."
        )

    warnings.append(
        f"Tesseract OCR strategy for {source_label}: {best_result['variant']} with {best_result['config']}."
    )

    warnings.extend(reconstruction["warnings"])

    return {
        "rows": rows,
        "warnings": warnings,
        "confidence": confidence_decimal if rows else 0.0,
        "isTableLike": reconstruction["isTableLike"],
    }


def extract_image_with_ocr(file_payload, image_bytes):
    try:
        return extract_image_text(file_payload, image_bytes)
    except Exception as error:
        fallback = extract_image_metadata(file_payload, image_bytes)
        fallback["warnings"].append(f"OCR failed: {str(error)}")
        return fallback
