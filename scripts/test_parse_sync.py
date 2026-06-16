import base64
import json
import sys
from pathlib import Path

import requests


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_parse_sync.py <path-to-pdf>")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    file_bytes = file_path.read_bytes()
    content_base64 = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "jobId": "local_test_fast_text",
        "parserMode": "FAST_TEXT",
        "files": [
            {
                "originalName": file_path.name,
                "mimeType": "application/pdf",
                "sizeBytes": len(file_bytes),
                "contentBase64": content_base64,
            }
        ],
    }

    response = requests.post(
        "http://localhost:8000/v1/parse/sync",
        json=payload,
        timeout=60,
    )

    print("Status:", response.status_code)

    try:
        data = response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        print(response.text)


if __name__ == "__main__":
    main()
