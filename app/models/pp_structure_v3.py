import inspect
import os
import threading

from app.core.config import normalize_ocr_quality_mode


class PPStructureV3Model:
    model_name = "pp_structure_v3"

    def __init__(self, language="en", quality_mode="BALANCED"):
        self.language = language
        self.quality_mode = normalize_ocr_quality_mode(quality_mode)
        self._pipeline = None
        self._lock = threading.Lock()

    def is_loaded(self):
        return self._pipeline is not None

    def get_runtime_options(self):
        if self.quality_mode == "HIGH_ACCURACY":
            return {
                "use_doc_orientation_classify": True,
                "use_doc_unwarping": True,
                "use_textline_orientation": True,
            }

        return {
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }

    def filter_supported_options(self, pipeline_class, options):
        signature = inspect.signature(pipeline_class)

        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            return options

        return {
            key: value
            for key, value in options.items()
            if key in signature.parameters
        }

    def load(self):
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline

            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")
            os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
            os.environ.setdefault(
                "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

            from paddleocr import PPStructureV3

            runtime_options = self.filter_supported_options(
                PPStructureV3,
                self.get_runtime_options(),
            )

            self._pipeline = PPStructureV3(**runtime_options)
            return self._pipeline

    def predict(self, input_path):
        pipeline = self.load()

        if hasattr(pipeline, "predict"):
            return pipeline.predict(str(input_path))

        raise RuntimeError("Unsupported PPStructureV3 runtime interface.")
