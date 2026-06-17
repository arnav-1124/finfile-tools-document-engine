from app.core.config import DEFAULT_OCR_LANGUAGE, DEFAULT_OCR_QUALITY_MODE, normalize_ocr_quality_mode
from app.models.paddle_ocr import PaddleOcrModel


class ParserMode:
    FAST_TEXT = "FAST_TEXT"
    OCR_TEXT = "OCR_TEXT"
    OCR_LAYOUT = "OCR_LAYOUT"
    OCR_TABLE = "OCR_TABLE"
    DOCUMENT_PARSE = "DOCUMENT_PARSE"


class ModelRegistry:
    def __init__(self):
        self._models = {}

    def get_loaded_models(self):
        return sorted(self._models.keys())

    def get_model_count(self):
        return len(self._models)

    def is_model_loaded(self, model_name):
        return model_name in self._models

    def register_model(self, model_name, model_instance):
        self._models[model_name] = model_instance
        return model_instance

    def get_model(self, model_name):
        return self._models.get(model_name)

    def get_paddle_ocr_model_name(self, language=DEFAULT_OCR_LANGUAGE, quality_mode=DEFAULT_OCR_QUALITY_MODE):
        normalized_quality_mode = normalize_ocr_quality_mode(quality_mode)
        return f"paddle_ocr_text_{language}_{normalized_quality_mode.lower()}"

    def get_paddle_ocr_model(self, language=DEFAULT_OCR_LANGUAGE, quality_mode=DEFAULT_OCR_QUALITY_MODE):
        normalized_quality_mode = normalize_ocr_quality_mode(quality_mode)
        model_name = self.get_paddle_ocr_model_name(
            language=language,
            quality_mode=normalized_quality_mode,
        )

        existing_model = self.get_model(model_name)

        if existing_model:
            return existing_model

        model = PaddleOcrModel(
            language=language,
            quality_mode=normalized_quality_mode,
        )
        model.load()

        return self.register_model(model_name, model)

    def get_status(self):
        return {
            "success": True,
            "modelCount": self.get_model_count(),
            "loadedModels": self.get_loaded_models(),
        }

    def warmup_paddle_ocr(self, language=DEFAULT_OCR_LANGUAGE, quality_mode=DEFAULT_OCR_QUALITY_MODE):
        normalized_quality_mode = normalize_ocr_quality_mode(quality_mode)
        model_name = self.get_paddle_ocr_model_name(
            language=language,
            quality_mode=normalized_quality_mode,
        )
        was_loaded = self.is_model_loaded(model_name)

        self.get_paddle_ocr_model(
            language=language,
            quality_mode=normalized_quality_mode,
        )

        return {
            "success": True,
            "message": "PaddleOCR model is ready.",
            "provider": "paddleocr",
            "modelName": model_name,
            "language": language,
            "qualityMode": normalized_quality_mode,
            "modelStatus": "warm" if was_loaded else "cold_start_loaded",
            "loadedModels": self.get_loaded_models(),
            "modelCount": self.get_model_count(),
        }

    def warmup(self, language=DEFAULT_OCR_LANGUAGE, quality_mode=DEFAULT_OCR_QUALITY_MODE):
        return self.warmup_paddle_ocr(
            language=language,
            quality_mode=quality_mode,
        )


model_registry = ModelRegistry()
