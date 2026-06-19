import base64

from fastapi import File, Form, UploadFile, APIRouter

from typing import Any, Dict

from pydantic import BaseModel

from app.core.config import DEFAULT_OCR_QUALITY_MODE, normalize_ocr_quality_mode
from app.core.errors import create_engine_error_response
from app.parsers.auto_parser import AutoParser
from app.parsers.fast_text_parser import FastTextParser
from app.parsers.ocr_text_parser import OcrTextParser
from app.parsers.document_parse_parser import DocumentParseParser


router = APIRouter(prefix="/v1/parse", tags=["parse"])


class ParsePayload(BaseModel):
    jobId: str | None = None
    parserMode: str = "FAST_TEXT"
    qualityMode: str | None = None
    language: str | None = None
    files: list[dict[str, Any]] = []


@router.post("/sync")
def parse_sync(payload: ParsePayload):
    try:
        data: Dict[str, Any] = payload.model_dump()
        parser_mode = data.get("parserMode") or "FAST_TEXT"

        data["qualityMode"] = normalize_ocr_quality_mode(
            data.get("qualityMode") or DEFAULT_OCR_QUALITY_MODE
        )

        if parser_mode == "FAST_TEXT":
            parser = FastTextParser()
        elif parser_mode == "OCR_TEXT":
            parser = OcrTextParser()
        elif parser_mode == "DOCUMENT_PARSE":
            parser = DocumentParseParser()
        elif parser_mode == "AUTO":
            parser = AutoParser()
        else:
            raise ValueError(f"Unsupported parser mode: {parser_mode}")

        return parser.parse(data)

    except Exception as error:
        return create_engine_error_response(
            str(error),
            code="DOCUMENT_PARSE_SYNC_ERROR",
        )


@router.post("/sync-file")
async def parse_sync_file(
    file: UploadFile = File(...),
    parserMode: str = Form("AUTO"),
    qualityMode: str = Form(DEFAULT_OCR_QUALITY_MODE),
    language: str = Form("en"),
):
    try:
        file_bytes = await file.read()

        payload = {
            "jobId": "direct_file_parse",
            "parserMode": parserMode,
            "qualityMode": normalize_ocr_quality_mode(qualityMode),
            "language": language,
            "files": [
                {
                    "originalName": file.filename,
                    "mimeType": file.content_type,
                    "sizeBytes": len(file_bytes),
                    "contentBase64": base64.b64encode(file_bytes).decode("utf-8"),
                }
            ],
        }

        if parserMode == "FAST_TEXT":
            parser = FastTextParser()
        elif parserMode == "OCR_TEXT":
            parser = OcrTextParser()
        elif parserMode == "DOCUMENT_PARSE":
            parser = DocumentParseParser()
        elif parserMode == "AUTO":
            parser = AutoParser()
        else:
            raise ValueError(f"Unsupported parser mode: {parserMode}")

        return parser.parse(payload)

    except Exception as error:
        return create_engine_error_response(
            str(error),
            code="DOCUMENT_PARSE_SYNC_FILE_ERROR",
        )
