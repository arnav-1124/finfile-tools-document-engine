import os


APP_NAME = "FinFile Document Engine"
APP_VERSION = "0.2.0"

PARSER_PREVIEW_LIMIT = int(os.getenv("PARSER_PREVIEW_LIMIT", "50"))
MAX_SYNC_PARSE_PAGES = int(os.getenv("MAX_SYNC_PARSE_PAGES", "10"))
MAX_SYNC_PARSE_BYTES = int(
    os.getenv("MAX_SYNC_PARSE_BYTES", str(25 * 1024 * 1024)))

DEFAULT_OCR_LANGUAGE = os.getenv("DEFAULT_OCR_LANGUAGE", "en")
DEFAULT_OCR_QUALITY_MODE = os.getenv("DEFAULT_OCR_QUALITY_MODE", "BALANCED")


class OcrQualityMode:
    FAST = "FAST"
    BALANCED = "BALANCED"
    HIGH_ACCURACY = "HIGH_ACCURACY"


SUPPORTED_OCR_QUALITY_MODES = {
    OcrQualityMode.FAST,
    OcrQualityMode.BALANCED,
    OcrQualityMode.HIGH_ACCURACY,
}

OCR_MAX_SIDE_BY_QUALITY_MODE = {
    OcrQualityMode.FAST: int(os.getenv("OCR_FAST_MAX_SIDE", "1600")),
    OcrQualityMode.BALANCED: int(os.getenv("OCR_BALANCED_MAX_SIDE", "2200")),
    OcrQualityMode.HIGH_ACCURACY: int(os.getenv("OCR_HIGH_ACCURACY_MAX_SIDE", "3200")),
}


def get_ocr_max_side(quality_mode):
    normalized_quality_mode = normalize_ocr_quality_mode(quality_mode)
    return OCR_MAX_SIDE_BY_QUALITY_MODE.get(
        normalized_quality_mode,
        OCR_MAX_SIDE_BY_QUALITY_MODE[OcrQualityMode.BALANCED],
    )


def normalize_ocr_quality_mode(value):
    quality_mode = str(value or DEFAULT_OCR_QUALITY_MODE).upper().strip()

    if quality_mode not in SUPPORTED_OCR_QUALITY_MODES:
        return DEFAULT_OCR_QUALITY_MODE

    return quality_mode
