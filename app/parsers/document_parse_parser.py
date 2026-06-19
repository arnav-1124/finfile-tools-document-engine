import base64
import tempfile
import time
from pathlib import Path

from app.core.config import DEFAULT_OCR_LANGUAGE, DEFAULT_OCR_QUALITY_MODE
from app.jobs.job_status import JobStatus
from app.models.registry import model_registry
from app.normalizers.document_parse_output import normalize_document_parse_result
from app.normalizers.parser_output import create_parser_output
from app.parsers.base import BaseParser
from app.preprocessors.pdf_renderer import render_pdf_pages_to_images


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def get_elapsed_ms(start_time):
    return int((time.perf_counter() - start_time) * 1000)


class DocumentParseParser(BaseParser):
    parser_mode = "DOCUMENT_PARSE"

    def parse(self, payload):
        parser_start_time = time.perf_counter()

        files = payload.get("files") or []

        if not files:
            raise ValueError(
                "At least one file is required for document parsing.")

        file_payload = files[0]
        content_base64 = file_payload.get("contentBase64")
        mime_type = file_payload.get("mimeType")

        if not content_base64:
            raise ValueError("File content is missing.")

        file_bytes = base64.b64decode(content_base64)

        language = payload.get("language") or DEFAULT_OCR_LANGUAGE
        quality_mode = payload.get("qualityMode") or DEFAULT_OCR_QUALITY_MODE

        model_name = model_registry.get_document_parse_model_name(
            language=language,
            quality_mode=quality_mode,
        )

        was_model_loaded = model_registry.is_model_loaded(model_name)

        model_load_start_time = time.perf_counter()
        model = model_registry.get_document_parse_model(
            language=language,
            quality_mode=quality_mode,
        )
        model_load_ms = get_elapsed_ms(model_load_start_time)

        page_count = 1
        render_ms = 0
        page_results = []
        raw_results = []

        if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            suffix = SUPPORTED_IMAGE_MIME_TYPES[mime_type]

            with tempfile.TemporaryDirectory() as temp_dir:
                input_path = Path(temp_dir) / f"document-parse-input{suffix}"
                input_path.write_bytes(file_bytes)

                page_start_time = time.perf_counter()
                raw_result = model.predict(input_path)
                page_ms = get_elapsed_ms(page_start_time)

                raw_results.append(raw_result)
                page_results.append(
                    {
                        "pageNumber": 1,
                        "parseMs": page_ms,
                    }
                )

        elif mime_type == "application/pdf":
            render_start_time = time.perf_counter()
            rendered_pdf = render_pdf_pages_to_images(file_bytes)
            render_ms = get_elapsed_ms(render_start_time)
            page_count = rendered_pdf["pageCount"]

            try:
                for page in rendered_pdf["pages"]:
                    page_start_time = time.perf_counter()
                    raw_result = model.predict(page["imagePath"])
                    page_ms = get_elapsed_ms(page_start_time)

                    raw_results.append(
                        {
                            "pageNumber": page["pageNumber"],
                            "result": raw_result,
                        }
                    )
                    page_results.append(
                        {
                            "pageNumber": page["pageNumber"],
                            "parseMs": page_ms,
                        }
                    )
            finally:
                rendered_pdf["tempDir"].cleanup()

        else:
            raise ValueError(
                "DOCUMENT_PARSE currently supports PDF, PNG, JPG, JPEG, and WebP files."
            )

        normalized_outputs = normalize_document_parse_result(raw_results)

        return create_parser_output(
            job_id=payload.get("jobId") or "sync_document_parse",
            parser_mode=self.parser_mode,
            status=JobStatus.COMPLETED,
            document={
                "originalName": file_payload.get("originalName"),
                "mimeType": mime_type,
                "sizeBytes": file_payload.get("sizeBytes"),
                "pageCount": page_count,
                "isScanned": True,
                "sourceType": "document_parse",
                "textBlockCount": len(
                    [
                        block
                        for block in normalized_outputs.get("documentBlocks", [])
                        if block.get("type") == "text"
                    ]
                ),
                "tableCount": len(normalized_outputs["tables"]),
            },
            outputs={
                "textBlocks": [],
                "plainText": normalized_outputs["plainText"],
                "structuredContent": normalized_outputs["structuredContent"],
                "documentBlocks": normalized_outputs["documentBlocks"],
                "tables": normalized_outputs["tables"],
                "markdown": normalized_outputs["markdown"],
                "json": normalized_outputs["json"],
            },
            confidence={
                "overall": None,
                "text": None,
                "tables": None,
            },
            warnings=[] if normalized_outputs["tables"] else [
                "No structured tables were detected."
            ],
            engine={
                "provider": "paddleocr",
                "parser": self.parser_mode,
                "strategy": "pp_structure_v3_document_parse",
                "qualityMode": quality_mode,
                "language": language,
                "modelName": model_name,
                "modelStatus": "warm" if was_model_loaded else "cold_start",
                "loadedModels": model_registry.get_loaded_models(),
            },
            performance={
                "totalMs": get_elapsed_ms(parser_start_time),
                "modelLoadMs": model_load_ms,
                "renderMs": render_ms,
                "pagesProcessed": page_count,
                "pagePerformance": page_results,
            },
        )
