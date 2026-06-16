from fastapi import APIRouter

from app.models.registry import model_registry


router = APIRouter(prefix="/v1/models", tags=["models"])


@router.get("/status")
def get_model_status():
    return {
        "success": True,
        "loadedModels": model_registry.get_loaded_models(),
        "registryReady": True,
    }


@router.post("/warmup")
def warmup_models():
    return model_registry.warmup()


@router.post("/warmup/paddle-ocr")
def warmup_paddle_ocr(language: str = "en"):
    model = model_registry.get_paddle_ocr_model(language=language)

    return {
        "success": True,
        "message": "PaddleOCR model is ready.",
        "language": language,
        "modelLoaded": model.is_loaded(),
        "loadedModels": model_registry.get_loaded_models(),
    }
