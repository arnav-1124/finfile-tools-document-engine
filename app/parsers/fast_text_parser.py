import base64
import fitz

from app.jobs.job_status import JobStatus
from app.normalizers.parser_output import create_parser_output
from app.normalizers.text_blocks import normalize_text_lines
from app.parsers.base import BaseParser


class FastTextParser(BaseParser):
    parser_mode = "FAST_TEXT"

    def parse(self, payload):
        files = payload.get("files") or []

        if not files:
            raise ValueError("At least one file is required for parsing.")

        file_payload = files[0]
        content_base64 = file_payload.get("contentBase64")

        if not content_base64:
            raise ValueError("File content is missing.")

        file_bytes = base64.b64decode(content_base64)
        mime_type = file_payload.get("mimeType")

        text_lines = []
        page_count = 1

        if mime_type == "application/pdf":
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = pdf_document.page_count

            for page_index in range(page_count):
                page = pdf_document.load_page(page_index)
                page_text = page.get_text("text") or ""

                for line in page_text.splitlines():
                    clean_line = line.strip()

                    if clean_line:
                        text_lines.append(
                            {
                                "text": clean_line,
                                "pageNumber": page_index + 1,
                            }
                        )

            pdf_document.close()
        else:
            raise ValueError("FAST_TEXT currently supports digital PDFs only.")

        text_blocks = normalize_text_lines(text_lines)

        return create_parser_output(
            job_id=payload.get("jobId") or "sync_parse",
            parser_mode=self.parser_mode,
            status=JobStatus.COMPLETED,
            document={
                "originalName": file_payload.get("originalName"),
                "mimeType": mime_type,
                "pageCount": page_count,
                "isScanned": len(text_blocks) == 0,
            },
            outputs={
                "textBlocks": text_blocks,
                "plainText": "\n".join(block["text"] for block in text_blocks),
                "tables": [],
                "markdown": "\n".join(block["text"] for block in text_blocks),
                "json": {
                    "textBlocks": text_blocks,
                },
            },
            confidence={
                "overall": 1 if text_blocks else 0,
            },
            warnings=[] if text_blocks else ["No embedded text was found."],
        )
