from app.core.config import OCR_PROVIDER
from app.providers.paddleocr_api_provider import PaddleOcrApiProvider


def get_document_parse_provider():
    if OCR_PROVIDER == "paddle_api":
        return PaddleOcrApiProvider()

    return None
