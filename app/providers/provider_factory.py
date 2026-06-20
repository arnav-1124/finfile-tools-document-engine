from app.core.config import OCR_PROVIDER
from app.providers.paddleocr_api_provider import PaddleOcrApiProvider


def get_document_parse_provider():
    print(f"[FinFile Provider] document parse provider={OCR_PROVIDER}")

    if OCR_PROVIDER == "paddle_api":
        print("[FinFile Provider] Using PaddleOCR API provider")
        return PaddleOcrApiProvider()

    print("[FinFile Provider] Using local Paddle fallback")
    return None
