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
