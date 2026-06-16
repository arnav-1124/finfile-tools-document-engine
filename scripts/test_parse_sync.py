import base64
import json
import mimetypes
import sys
from pathlib import Path

import requests


def guess_parser_mode(mime_type):
    if mime_type == "application/pdf":
        return "FAST_TEXT"

    if mime_type in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
        return "OCR_TEXT"

    return "FAST_TEXT"


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/test_parse_sync.py <path-to-file> [parser-mode]")
        print("Example PDF: python scripts/test_parse_sync.py sample.pdf FAST_TEXT")
        print("Example image: python scripts/test_parse_sync.py sample.png OCR_TEXT")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    parser_mode = sys.argv[2] if len(
        sys.argv) >= 3 else guess_parser_mode(mime_type)

    file_bytes = file_path.read_bytes()
    content_base64 = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "jobId": f"local_test_{parser_mode.lower()}",
        "parserMode": parser_mode,
        "files": [
            {
                "originalName": file_path.name,
                "mimeType": mime_type,
                "sizeBytes": len(file_bytes),
                "contentBase64": content_base64,
            }
        ],
    }

    response = requests.post(
        "http://localhost:8000/v1/parse/sync",
        json=payload,
        timeout=120,
    )

    print("Status:", response.status_code)

    try:
        data = response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        print(response.text)


if __name__ == "__main__":
    main()
