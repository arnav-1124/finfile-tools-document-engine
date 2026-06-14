import json
import sys
import traceback

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

from app.services.pdf_image_to_excel import extract_pdf_image_to_excel
from app.utils.file_helpers import create_error_response


app = FastAPI(title="FinFile Document Engine", version="0.1.0")


class EnginePayload(BaseModel):
    tool: str
    files: list[dict[str, Any]] = []
    extractionMode: str | None = None


@app.get("/health")
def health_check():
    return {
        "success": True,
        "service": "finfile-document-engine",
        "status": "healthy",
    }


@app.post("/extract")
def extract_document(payload: EnginePayload):
    try:
        data: Dict[str, Any] = payload.model_dump()

        if data.get("tool") != "pdf-image-to-excel":
            raise ValueError(f"Unsupported tool: {data.get('tool')}")

        return extract_pdf_image_to_excel(data)

    except Exception as error:
        response = create_error_response(
            str(error),
            code="DOCUMENT_ENGINE_RUNTIME_ERROR",
        )
        response["trace"] = traceback.format_exc()
        return response


def main():
    try:
        raw_input = sys.stdin.read()

        if not raw_input:
            raise ValueError("Document engine received empty payload.")

        payload = json.loads(raw_input)
        tool = payload.get("tool")

        if tool != "pdf-image-to-excel":
            raise ValueError(f"Unsupported tool: {tool}")

        result = extract_pdf_image_to_excel(payload)

        print(json.dumps(result, ensure_ascii=False))

    except Exception as error:
        response = create_error_response(
            str(error),
            code="DOCUMENT_ENGINE_RUNTIME_ERROR",
        )

        response["trace"] = traceback.format_exc()

        print(json.dumps(response, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
