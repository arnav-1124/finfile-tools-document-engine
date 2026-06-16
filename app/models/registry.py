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

    def is_model_loaded(self, model_name):
        return model_name in self._models

    def register_model(self, model_name, model_instance):
        self._models[model_name] = model_instance
        return model_instance

    def get_model(self, model_name):
        return self._models.get(model_name)

    def warmup(self):
        return {
            "success": True,
            "message": "Model registry is ready.",
            "loadedModels": self.get_loaded_models(),
        }


model_registry = ModelRegistry()
