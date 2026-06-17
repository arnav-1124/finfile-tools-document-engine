import os
import threading

from app.core.config import OcrQualityMode, normalize_ocr_quality_mode


class PaddleOcrModel:
    model_name = "paddle_ocr_text"

    def __init__(self, language="en", quality_mode="BALANCED"):
        self.language = language
        self.quality_mode = normalize_ocr_quality_mode(quality_mode)
        self._ocr = None
        self._lock = threading.Lock()

    def is_loaded(self):
        return self._ocr is not None

    def get_runtime_options(self):
        if self.quality_mode == OcrQualityMode.HIGH_ACCURACY:
            return {
                "lang": self.language,
                "use_doc_orientation_classify": True,
                "use_doc_unwarping": True,
                "use_textline_orientation": True,
            }

        if self.quality_mode == OcrQualityMode.FAST:
            return {
                "lang": self.language,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            }

        return {
            "lang": self.language,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }

    def load(self):
        with self._lock:
            if self._ocr is not None:
                return self._ocr

            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")
            os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")

            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(**self.get_runtime_options())
            return self._ocr

    def predict(self, image_path_or_array):
        ocr = self.load()

        if hasattr(ocr, "predict"):
            return ocr.predict(image_path_or_array)

        if hasattr(ocr, "ocr"):
            try:
                return ocr.ocr(image_path_or_array, cls=True)
            except TypeError:
                return ocr.ocr(image_path_or_array)

        raise RuntimeError("Unsupported PaddleOCR runtime interface.")
