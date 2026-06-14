from app.services.table_reconstructor import reconstruct_table_from_ocr_lines
from PIL import Image
import io
import os
import tempfile
from functools import lru_cache

# Important: these must be set before Paddle/PaddleOCR is imported.
# They avoid some Windows CPU runtime / oneDNN / PIR execution issues.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")


@lru_cache(maxsize=1)
def get_paddle_ocr():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def save_pil_image_to_temp_path(image):
    image = image.convert("RGB")

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False,
    )

    temp_path = temp_file.name
    temp_file.close()

    image.save(temp_path)

    return temp_path


def extract_texts_from_paddle_prediction(prediction_result):
    lines = []
    confidences = []

    if not prediction_result:
        return lines, confidences

    for result_item in prediction_result:
        json_data = None

        if hasattr(result_item, "json"):
            try:
                json_data = result_item.json
            except Exception:
                json_data = None

        if callable(json_data):
            try:
                json_data = json_data()
            except Exception:
                json_data = None

        if isinstance(json_data, dict):
            result_data = json_data.get("res", json_data)

            rec_texts = result_data.get(
                "rec_texts") or result_data.get("texts") or []
            rec_scores = result_data.get(
                "rec_scores") or result_data.get("scores") or []

            for text in rec_texts:
                clean_text = str(text).strip()
                if clean_text:
                    lines.append(clean_text)

            for score in rec_scores:
                try:
                    confidences.append(float(score))
                except (TypeError, ValueError):
                    continue

            continue

        if hasattr(result_item, "res"):
            result_data = getattr(result_item, "res", {}) or {}

            rec_texts = result_data.get(
                "rec_texts") or result_data.get("texts") or []
            rec_scores = result_data.get(
                "rec_scores") or result_data.get("scores") or []

            for text in rec_texts:
                clean_text = str(text).strip()
                if clean_text:
                    lines.append(clean_text)

            for score in rec_scores:
                try:
                    confidences.append(float(score))
                except (TypeError, ValueError):
                    continue

    return lines, confidences


def calculate_average_confidence(confidences):
    if not confidences:
        return 0.0

    return round(sum(confidences) / len(confidences), 2)


def extract_with_paddle_from_pil_image(image):
    temp_path = None

    try:
        temp_path = save_pil_image_to_temp_path(image)

        ocr = get_paddle_ocr()

        if hasattr(ocr, "predict"):
            prediction_result = ocr.predict(temp_path)
        else:
            prediction_result = ocr.ocr(temp_path)

        lines, confidences = extract_texts_from_paddle_prediction(
            prediction_result)

        reconstruction = reconstruct_table_from_ocr_lines(lines)
        average_confidence = calculate_average_confidence(confidences)

        return {
            "success": True,
            "lines": lines,
            "columns": reconstruction["columns"],
            "rows": reconstruction["rows"],
            "isTableLike": reconstruction["isTableLike"],
            "confidence": average_confidence,
            "warnings": [
                f"PaddleOCR extracted {len(lines)} text lines.",
                *reconstruction["warnings"],
            ],
        }

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def extract_with_paddle_from_image_bytes(image_bytes):
    import io

    image = Image.open(io.BytesIO(image_bytes))
    return extract_with_paddle_from_pil_image(image)
