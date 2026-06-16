import base64
import tempfile
from pathlib import Path

from app.jobs.job_status import JobStatus
from app.models.registry import model_registry
from app.normalizers.parser_output import create_parser_output
from app.normalizers.text_blocks import create_text_block
from app.parsers.base import BaseParser


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def convert_bbox_to_list(bbox):
    if bbox is None:
        return None

    if hasattr(bbox, "tolist"):
        return bbox.tolist()

    if isinstance(bbox, list):
        normalized = []

        for point in bbox:
            if hasattr(point, "tolist"):
                normalized.append(point.tolist())
            else:
                normalized.append(point)

        return normalized

    return bbox


def extract_text_items_from_paddle_result(result):
    text_items = []

    if not result:
        return text_items

    if isinstance(result, list):
        for page_result in result:
            if not page_result:
                continue

            # New PaddleOCR result format:
            # {
            #   "rec_texts": [...],
            #   "rec_scores": [...],
            #   "rec_polys": [...]
            # }
            if isinstance(page_result, dict):
                rec_texts = page_result.get("rec_texts") or []
                rec_scores = page_result.get("rec_scores") or []
                rec_polys = (
                    page_result.get("rec_polys")
                    or page_result.get("dt_polys")
                    or []
                )

                for index, text in enumerate(rec_texts):
                    clean_text = str(text or "").strip()

                    if not clean_text:
                        continue

                    confidence = (
                        float(rec_scores[index])
                        if index < len(rec_scores)
                        else None
                    )

                    bbox = (
                        convert_bbox_to_list(rec_polys[index])
                        if index < len(rec_polys)
                        else None
                    )

                    text_items.append(
                        {
                            "text": clean_text,
                            "confidence": confidence,
                            "bbox": bbox,
                        }
                    )

                continue

            # Older PaddleOCR result format:
            # [
            #   [bbox, ("text", confidence)],
            #   ...
            # ]
            if isinstance(page_result, list):
                for item in page_result:
                    if not item or len(item) < 2:
                        continue

                    bbox = item[0]
                    text_meta = item[1]

                    if (
                        isinstance(text_meta, (list, tuple))
                        and len(text_meta) >= 2
                    ):
                        text = str(text_meta[0] or "").strip()
                        confidence = float(text_meta[1] or 0)

                        if text:
                            text_items.append(
                                {
                                    "text": text,
                                    "confidence": confidence,
                                    "bbox": convert_bbox_to_list(bbox),
                                }
                            )

    return text_items


class OcrTextParser(BaseParser):
    parser_mode = "OCR_TEXT"

    def parse(self, payload):
        files = payload.get("files") or []

        if not files:
            raise ValueError(
                "At least one image file is required for OCR parsing.")

        file_payload = files[0]
        content_base64 = file_payload.get("contentBase64")
        mime_type = file_payload.get("mimeType")

        if not content_base64:
            raise ValueError("File content is missing.")

        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ValueError(
                "OCR_TEXT currently supports PNG, JPG, JPEG, and WebP images.")

        file_bytes = base64.b64decode(content_base64)
        suffix = SUPPORTED_IMAGE_MIME_TYPES[mime_type]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / f"ocr-input{suffix}"
            temp_path.write_bytes(file_bytes)

            model = model_registry.get_paddle_ocr_model(language="en")
            raw_result = model.predict(str(temp_path))

        text_items = extract_text_items_from_paddle_result(raw_result)

        text_blocks = [
            create_text_block(
                text=item["text"],
                page_number=1,
                confidence=item.get("confidence"),
                bbox=item.get("bbox"),
                block_type="text",
            )
            for item in text_items
        ]

        plain_text = "\n".join(block["text"] for block in text_blocks)

        confidence_values = [
            block["confidence"]
            for block in text_blocks
            if block.get("confidence") is not None
        ]

        overall_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0
        )

        return create_parser_output(
            job_id=payload.get("jobId") or "sync_ocr_text",
            parser_mode=self.parser_mode,
            status=JobStatus.COMPLETED,
            document={
                "originalName": file_payload.get("originalName"),
                "mimeType": mime_type,
                "pageCount": 1,
                "isScanned": True,
            },
            outputs={
                "textBlocks": text_blocks,
                "plainText": plain_text,
                "tables": [],
                "markdown": plain_text,
                "json": {
                    "textBlocks": text_blocks,
                },
            },
            confidence={
                "overall": overall_confidence,
            },
            warnings=[] if text_blocks else ["No OCR text was detected."],
        )
