import os
import threading


class PaddleOcrModel:
    model_name = "paddle_ocr_text"

    def __init__(self, language="en"):
        self.language = language
        self._ocr = None
        self._lock = threading.Lock()

    def is_loaded(self):
        return self._ocr is not None

    def load(self):
        with self._lock:
            if self._ocr is not None:
                return self._ocr

            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")

            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(lang=self.language)
            return self._ocr

    def predict(self, image_path_or_array):
        ocr = self.load()

        # New PaddleOCR interface
        if hasattr(ocr, "predict"):
            return ocr.predict(image_path_or_array)

        # Older PaddleOCR interface
        if hasattr(ocr, "ocr"):
            try:
                return ocr.ocr(image_path_or_array, cls=True)
            except TypeError:
                return ocr.ocr(image_path_or_array)

        raise RuntimeError("Unsupported PaddleOCR runtime interface.")
