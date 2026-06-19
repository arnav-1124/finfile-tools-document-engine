import os
import threading


class PPStructureV3Model:
    model_name = "pp_structure_v3"

    def __init__(self, language="en", quality_mode="BALANCED"):
        self.language = language
        self.quality_mode = quality_mode
        self._pipeline = None
        self._lock = threading.Lock()

    def is_loaded(self):
        return self._pipeline is not None

    def get_runtime_options(self):
        return {
            "use_doc_orientation_classify": True,
            "use_doc_unwarping": True,
            "use_textline_orientation": True,
        }

    def load(self):
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline

            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")
            os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")

            from paddleocr import PPStructureV3

            self._pipeline = PPStructureV3(**self.get_runtime_options())
            return self._pipeline

    def predict(self, input_path):
        pipeline = self.load()

        if hasattr(pipeline, "predict"):
            return pipeline.predict(str(input_path))

        raise RuntimeError("Unsupported PPStructureV3 runtime interface.")
