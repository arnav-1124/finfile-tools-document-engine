import time

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import DEFAULT_OCR_LANGUAGE
from app.models.registry import model_registry


router = APIRouter(prefix="/v1/models", tags=["models"])


class WarmupPayload(BaseModel):
    language: str | None = None


def get_elapsed_ms(start_time):
    return int((time.perf_counter() - start_time) * 1000)


@router.get("/status")
def get_models_status():
    return {
        "success": True,
        "service": "finfile-document-engine",
        "models": model_registry.get_status(),
    }


@router.post("/warmup")
def warmup_models(payload: WarmupPayload | None = None):
    start_time = time.perf_counter()

    language = DEFAULT_OCR_LANGUAGE

    if payload and payload.language:
        language = payload.language

    warmup_result = model_registry.warmup(language=language)

    return {
        "success": True,
        "service": "finfile-document-engine",
        "warmup": warmup_result,
        "performance": {
            "warmupMs": get_elapsed_ms(start_time),
        },
    }
