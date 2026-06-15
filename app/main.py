import json
import sys
import traceback

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

from app.services.pdf_image_to_excel import extract_pdf_image_to_excel
from app.utils.file_helpers import create_error_response
from app.services.pdf_to_images import convert_pdf_to_images


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

        tool = data.get("tool")

        if tool == "pdf-image-to-excel":
            return extract_pdf_image_to_excel(data)

        if tool == "pdf-to-images":
            return convert_pdf_to_images(data)

        raise ValueError(f"Unsupported tool: {tool}")

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

        if tool == "pdf-image-to-excel":
            result = extract_pdf_image_to_excel(payload)
        elif tool == "pdf-to-images":
            result = convert_pdf_to_images(payload)
        else:
            raise ValueError(f"Unsupported tool: {tool}")

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
