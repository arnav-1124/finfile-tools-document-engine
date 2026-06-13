import json
import sys
import traceback

from app.services.pdf_image_to_excel import extract_pdf_image_to_excel
from app.utils.file_helpers import create_error_response


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