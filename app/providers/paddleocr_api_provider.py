import json
import time

import requests

from app.core.config import (
    PADDLEOCR_API_MODEL,
    PADDLEOCR_API_POLL_INTERVAL_SECONDS,
    PADDLEOCR_API_TIMEOUT_SECONDS,
    PADDLEOCR_API_TOKEN,
    PADDLEOCR_API_URL,
)
from app.normalizers.paddleocr_api_output import normalize_paddleocr_api_jsonl


def get_elapsed_ms(start_time):
    return int((time.perf_counter() - start_time) * 1000)


class PaddleOcrApiProvider:
    provider_name = "paddleocr_api"

    def __init__(self):
        if not PADDLEOCR_API_TOKEN:
            raise ValueError("PADDLEOCR_API_TOKEN is missing.")

        self.job_url = PADDLEOCR_API_URL
        self.token = PADDLEOCR_API_TOKEN
        self.model = PADDLEOCR_API_MODEL

    def get_headers(self):
        return {
            "Authorization": f"bearer {self.token}",
        }

    def submit_job(self, file_payload):
        original_name = file_payload.get("originalName") or "document"
        content = file_payload.get("bytes")

        if not content:
            raise ValueError(
                "File bytes are missing for PaddleOCR API request.")

        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        data = {
            "model": self.model,
            "optionalPayload": json.dumps(optional_payload),
        }

        files = {
            "file": (original_name, content, file_payload.get("mimeType")),
        }

        response = requests.post(
            self.job_url,
            headers=self.get_headers(),
            data=data,
            files=files,
            timeout=120,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"PaddleOCR API job submission failed with status {response.status_code}: {response.text}"
            )

        data = response.json()

        try:
            return data["data"]["jobId"]
        except KeyError as error:
            raise RuntimeError(
                f"PaddleOCR API job response did not include jobId: {data}"
            ) from error

    def poll_job(self, job_id):
        started_at = time.perf_counter()

        while True:
            response = requests.get(
                f"{self.job_url}/{job_id}",
                headers=self.get_headers(),
                timeout=60,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"PaddleOCR API job polling failed with status {response.status_code}: {response.text}"
                )

            data = response.json().get("data", {})
            state = data.get("state")

            if state == "done":
                result_url = (data.get("resultUrl") or {}).get("jsonUrl")

                if not result_url:
                    raise RuntimeError(
                        "PaddleOCR API result jsonUrl is missing.")

                return {
                    "state": state,
                    "resultUrl": result_url,
                    "extractProgress": data.get("extractProgress") or {},
                    "pollMs": get_elapsed_ms(started_at),
                }

            if state == "failed":
                raise RuntimeError(
                    data.get("errorMsg") or "PaddleOCR API job failed."
                )

            if get_elapsed_ms(started_at) > PADDLEOCR_API_TIMEOUT_SECONDS * 1000:
                raise TimeoutError("PaddleOCR API job timed out.")

            time.sleep(PADDLEOCR_API_POLL_INTERVAL_SECONDS)

    def download_jsonl(self, jsonl_url):
        response = requests.get(jsonl_url, timeout=120)
        response.raise_for_status()
        return response.text

    def parse_document(self, file_payload):
        started_at = time.perf_counter()

        submit_start = time.perf_counter()
        job_id = self.submit_job(file_payload)
        submit_ms = get_elapsed_ms(submit_start)

        poll_result = self.poll_job(job_id)

        download_start = time.perf_counter()
        jsonl_text = self.download_jsonl(poll_result["resultUrl"])
        download_ms = get_elapsed_ms(download_start)

        normalized = normalize_paddleocr_api_jsonl(jsonl_text)

        return {
            "jobId": job_id,
            "outputs": normalized,
            "pageCount": normalized.get("pageCount") or 1,
            "engine": {
                "provider": self.provider_name,
                "modelName": self.model,
                "strategy": "paddleocr_vl_api_document_parse",
                "apiJobId": job_id,
            },
            "performance": {
                "totalMs": get_elapsed_ms(started_at),
                "submitMs": submit_ms,
                "pollMs": poll_result["pollMs"],
                "downloadMs": download_ms,
                "apiProgress": poll_result.get("extractProgress") or {},
            },
        }
