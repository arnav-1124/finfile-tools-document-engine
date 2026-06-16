from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.errors import create_engine_error_response
from app.parsers.fast_text_parser import FastTextParser


router = APIRouter(prefix="/v1/parse", tags=["parse"])


class ParsePayload(BaseModel):
    jobId: str | None = None
    parserMode: str = "FAST_TEXT"
    files: list[dict[str, Any]] = []


@router.post("/sync")
def parse_sync(payload: ParsePayload):
    try:
        data: Dict[str, Any] = payload.model_dump()
        parser_mode = data.get("parserMode") or "FAST_TEXT"

        if parser_mode != "FAST_TEXT":
            raise ValueError(f"Unsupported parser mode: {parser_mode}")

        parser = FastTextParser()
        return parser.parse(data)

    except Exception as error:
        return create_engine_error_response(
            str(error),
            code="DOCUMENT_PARSE_SYNC_ERROR",
        )
