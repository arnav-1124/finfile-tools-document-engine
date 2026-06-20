import base64
import tempfile
import time
from pathlib import Path

from app.jobs.job_status import JobStatus
from app.models.registry import model_registry
from app.normalizers.parser_output import create_parser_output
from app.normalizers.text_blocks import create_text_block
from app.parsers.base import BaseParser
from app.preprocessors.pdf_renderer import render_pdf_pages_to_images
from app.preprocessors.ocr_image_optimizer import optimize_image_for_ocr
from app.core.config import use_paddleocr_api


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def get_elapsed_ms(start_time):
    return int((time.perf_counter() - start_time) * 1000)


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


def run_paddle_ocr_on_image(model, image_path, page_number, quality_mode="BALANCED"):
    page_start_time = time.perf_counter()

    optimization_start_time = time.perf_counter()
    optimized_image = optimize_image_for_ocr(
        image_path=image_path,
        quality_mode=quality_mode,
    )
    optimization_ms = get_elapsed_ms(optimization_start_time)

    raw_result = model.predict(optimized_image["imagePath"])
    text_items = extract_text_items_from_paddle_result(raw_result)

    text_blocks = [
        create_text_block(
            text=item["text"],
            page_number=page_number,
            confidence=item.get("confidence"),
            bbox=item.get("bbox"),
            block_type="text",
        )
        for item in text_items
    ]

    confidence_values = [
        block["confidence"]
        for block in text_blocks
        if block.get("confidence") is not None
    ]

    average_confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values
        else 0
    )

    return {
        "pageNumber": page_number,
        "textBlocks": text_blocks,
        "textBlockCount": len(text_blocks),
        "averageConfidence": average_confidence,
        "ocrMs": get_elapsed_ms(page_start_time),
        "optimizationMs": optimization_ms,
        "imageOptimization": optimized_image,
    }


class OcrTextParser(BaseParser):
    parser_mode = "OCR_TEXT"

    def parse(self, payload):
        parser_start_time = time.perf_counter()

        files = payload.get("files") or []

        if not files:
            raise ValueError("At least one file is required for OCR parsing.")

        if use_paddleocr_api():
            from app.parsers.document_parse_parser import DocumentParseParser

            document_result = DocumentParseParser().parse(
                {
                    **payload,
                    "parserMode": "DOCUMENT_PARSE",
                }
            )

            document_result["parserMode"] = self.parser_mode
            document_result["selectedParser"] = "DOCUMENT_PARSE"

            return document_result

        file_payload = files[0]
        content_base64 = file_payload.get("contentBase64")
        mime_type = file_payload.get("mimeType")

        if not content_base64:
            raise ValueError("File content is missing.")

        decode_start_time = time.perf_counter()
        file_bytes = base64.b64decode(content_base64)
        decode_ms = get_elapsed_ms(decode_start_time)

        quality_mode = payload.get("qualityMode") or "BALANCED"
        language = payload.get("language") or "en"

        model_name = model_registry.get_paddle_ocr_model_name(
            language=language,
            quality_mode=quality_mode,
        )
        was_model_loaded = model_registry.is_model_loaded(model_name)

        model_load_start_time = time.perf_counter()
        model = model_registry.get_paddle_ocr_model(
            language=language,
            quality_mode=quality_mode,
        )
        model_load_ms = get_elapsed_ms(model_load_start_time)

        text_blocks = []
        page_count = 1
        page_performance = []
        render_ms = 0
        source_type = "unknown"

        if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            source_type = "image"
            suffix = SUPPORTED_IMAGE_MIME_TYPES[mime_type]

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / f"ocr-input{suffix}"
                temp_path.write_bytes(file_bytes)

                page_result = run_paddle_ocr_on_image(
                    model=model,
                    image_path=temp_path,
                    page_number=1,
                    quality_mode=quality_mode,
                )

                text_blocks.extend(page_result["textBlocks"])
                page_performance.append(
                    {
                        "pageNumber": page_result["pageNumber"],
                        "ocrMs": page_result["ocrMs"],
                        "textBlockCount": page_result["textBlockCount"],
                        "averageConfidence": page_result["averageConfidence"],
                        "optimizationMs": page_result["optimizationMs"],
                        "imageOptimization": page_result["imageOptimization"],
                    }
                )

        elif mime_type == "application/pdf":
            source_type = "scanned_pdf"

            render_start_time = time.perf_counter()
            rendered_pdf = render_pdf_pages_to_images(file_bytes)
            render_ms = get_elapsed_ms(render_start_time)
            page_count = rendered_pdf["pageCount"]

            try:
                for page in rendered_pdf["pages"]:
                    page_result = run_paddle_ocr_on_image(
                        model=model,
                        image_path=page["imagePath"],
                        page_number=page["pageNumber"],
                        quality_mode=quality_mode,
                    )

                    text_blocks.extend(page_result["textBlocks"])
                    page_performance.append(
                        {
                            "pageNumber": page_result["pageNumber"],
                            "ocrMs": page_result["ocrMs"],
                            "textBlockCount": page_result["textBlockCount"],
                            "averageConfidence": page_result["averageConfidence"],
                            "optimizationMs": page_result["optimizationMs"],
                            "imageOptimization": page_result["imageOptimization"],
                        }
                    )
            finally:
                rendered_pdf["tempDir"].cleanup()

        else:
            raise ValueError(
                "OCR_TEXT currently supports PDF, PNG, JPG, JPEG, and WebP files."
            )

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

        warnings = []

        if not text_blocks:
            warnings.append("No OCR text was detected.")

        if text_blocks and overall_confidence < 0.55:
            warnings.append(
                "OCR confidence is low. Please review the extracted text carefully."
            )

        return create_parser_output(
            job_id=payload.get("jobId") or "sync_ocr_text",
            parser_mode=self.parser_mode,
            status=JobStatus.COMPLETED,
            document={
                "originalName": file_payload.get("originalName"),
                "mimeType": mime_type,
                "sizeBytes": file_payload.get("sizeBytes"),
                "pageCount": page_count,
                "isScanned": True,
                "sourceType": source_type,
                "textBlockCount": len(text_blocks),
            },
            outputs={
                "textBlocks": text_blocks,
                "plainText": plain_text,
                "tables": [],
                "markdown": plain_text,
                "json": {
                    "textBlocks": text_blocks,
                    "pagePerformance": page_performance,
                },
            },
            confidence={
                "overall": overall_confidence,
                "text": overall_confidence,
            },
            warnings=warnings,
            engine={
                "provider": "paddleocr",
                "parser": self.parser_mode,
                "strategy": "ocr_text_blocks",
                "qualityMode": quality_mode,
                "language": language,
                "modelName": model_name,
                "modelStatus": "warm" if was_model_loaded else "cold_start",
                "loadedModels": model_registry.get_loaded_models(),
            },
            performance={
                "totalMs": get_elapsed_ms(parser_start_time),
                "decodeMs": decode_ms,
                "modelLoadMs": model_load_ms,
                "renderMs": render_ms,
                "pagesProcessed": page_count,
                "pagePerformance": page_performance,
            },
        )
