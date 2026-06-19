import json
import os
import requests
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


JOB_URL = os.getenv(
    "PADDLEOCR_API_URL",
    "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
)

TOKEN = os.getenv("PADDLEOCR_API_TOKEN")
MODEL = os.getenv("PADDLEOCR_API_MODEL", "PaddleOCR-VL-1.6")


def fail(message):
    print(f"ERROR: {message}")
    sys.exit(1)


def submit_job(file_path):
    if not TOKEN:
        fail("PADDLEOCR_API_TOKEN is missing.")

    headers = {
        "Authorization": f"bearer {TOKEN}",
    }

    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }

    print(f"Processing file: {file_path}")
    print(f"Using model: {MODEL}")

    if file_path.startswith("http"):
        headers["Content-Type"] = "application/json"

        payload = {
            "fileUrl": file_path,
            "model": MODEL,
            "optionalPayload": optional_payload,
        }

        response = requests.post(
            JOB_URL,
            json=payload,
            headers=headers,
            timeout=60,
        )
    else:
        if not os.path.exists(file_path):
            fail(f"File not found: {file_path}")

        data = {
            "model": MODEL,
            "optionalPayload": json.dumps(optional_payload),
        }

        with open(file_path, "rb") as file:
            files = {"file": file}
            response = requests.post(
                JOB_URL,
                headers=headers,
                data=data,
                files=files,
                timeout=120,
            )

    print(f"Submit status: {response.status_code}")

    if response.status_code != 200:
        print(response.text)
        fail("Job submission failed.")

    data = response.json()
    job_id = data["data"]["jobId"]

    print(f"Job submitted successfully: {job_id}")
    return job_id


def poll_job(job_id):
    headers = {
        "Authorization": f"bearer {TOKEN}",
    }

    while True:
        response = requests.get(
            f"{JOB_URL}/{job_id}",
            headers=headers,
            timeout=60,
        )

        print(f"Poll status: {response.status_code}")

        if response.status_code != 200:
            print(response.text)
            fail("Job polling failed.")

        data = response.json()["data"]
        state = data["state"]

        if state == "pending":
            print("Job pending...")

        elif state == "running":
            progress = data.get("extractProgress", {})
            total_pages = progress.get("totalPages")
            extracted_pages = progress.get("extractedPages")

            if total_pages is not None:
                print(
                    f"Job running... extracted {extracted_pages}/{total_pages} pages"
                )
            else:
                print("Job running...")

        elif state == "done":
            progress = data.get("extractProgress", {})
            print("Job completed.")
            print(json.dumps(progress, indent=2, ensure_ascii=False))

            result_url = data.get("resultUrl", {}).get("jsonUrl")

            if not result_url:
                fail("Result jsonUrl missing.")

            return result_url

        elif state == "failed":
            fail(data.get("errorMsg", "Job failed."))

        else:
            print(f"Unknown state: {state}")

        time.sleep(5)


def download_results(jsonl_url):
    output_dir = Path("output/paddleocr_api_test")
    output_dir.mkdir(parents=True, exist_ok=True)

    response = requests.get(jsonl_url, timeout=120)
    response.raise_for_status()

    jsonl_path = output_dir / "result.jsonl"
    jsonl_path.write_text(response.text, encoding="utf-8")

    print(f"Raw JSONL saved at: {jsonl_path}")

    markdown_parts = []
    parsed_pages = []

    lines = response.text.strip().splitlines()

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        item = json.loads(line)
        result = item.get("result", {})

        layout_results = result.get("layoutParsingResults", [])

        for page_index, layout_result in enumerate(layout_results, start=1):
            markdown = layout_result.get("markdown", {})
            markdown_text = markdown.get("text", "")

            if markdown_text:
                markdown_parts.append(markdown_text)

                md_path = output_dir / f"page_{line_number}_{page_index}.md"
                md_path.write_text(markdown_text, encoding="utf-8")
                print(f"Markdown saved at: {md_path}")

            parsed_pages.append(
                {
                    "lineNumber": line_number,
                    "pageIndex": page_index,
                    "hasMarkdown": bool(markdown_text),
                    "markdownLength": len(markdown_text),
                    "imageCount": len(markdown.get("images", {}) or {}),
                    "outputImageCount": len(layout_result.get("outputImages", {}) or {}),
                    "keys": list(layout_result.keys()),
                }
            )

    combined_md = "\n\n---\n\n".join(markdown_parts)
    combined_path = output_dir / "combined.md"
    combined_path.write_text(combined_md, encoding="utf-8")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "pageCount": len(parsed_pages),
                "pages": parsed_pages,
                "combinedMarkdownLength": len(combined_md),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Combined markdown saved at: {combined_path}")
    print(f"Summary saved at: {summary_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        fail("Usage: python scripts/test_paddleocr_api.py <file_path_or_url>")

    file_path_arg = sys.argv[1]

    job_id = submit_job(file_path_arg)
    result_jsonl_url = poll_job(job_id)
    download_results(result_jsonl_url)
