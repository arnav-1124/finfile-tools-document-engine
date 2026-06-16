from app.parsers.base import BaseParser
from app.parsers.fast_text_parser import FastTextParser
from app.parsers.ocr_text_parser import OcrTextParser


MIN_DIGITAL_TEXT_CHARS = 40
MIN_DIGITAL_TEXT_LINES = 6

FORM_TEMPLATE_KEYWORDS = [
    "date______________",
    "order no.",
    "qty",
    "description",
    "price",
    "total",
    "from",
    "to",
]


def get_plain_text(result):
    return result.get("outputs", {}).get("plainText", "") or ""


def get_text_blocks(result):
    return result.get("outputs", {}).get("textBlocks", []) or []


def has_template_placeholders(text):
    normalized_text = text.lower()

    return (
        "____" in normalized_text
        or "____________" in normalized_text
        or normalized_text.count("_") >= 5
    )


def looks_like_sparse_form_template(text_blocks, plain_text):
    clean_lines = [
        str(block.get("text") or "").strip()
        for block in text_blocks
        if str(block.get("text") or "").strip()
    ]

    if not clean_lines:
        return True

    normalized_text = plain_text.lower()

    matched_keywords = sum(
        1 for keyword in FORM_TEMPLATE_KEYWORDS if keyword in normalized_text
    )

    has_short_label_heavy_output = (
        len(clean_lines) <= 15
        and matched_keywords >= 5
    )

    return has_template_placeholders(plain_text) or has_short_label_heavy_output


def should_use_fast_text(fast_result):
    plain_text = get_plain_text(fast_result)
    text_blocks = get_text_blocks(fast_result)

    if len(plain_text.strip()) < MIN_DIGITAL_TEXT_CHARS:
        return False

    if len(text_blocks) < MIN_DIGITAL_TEXT_LINES:
        return False

    if looks_like_sparse_form_template(text_blocks, plain_text):
        return False

    return True


class AutoParser(BaseParser):
    parser_mode = "AUTO"

    def parse(self, payload):
        files = payload.get("files") or []

        if not files:
            raise ValueError("At least one file is required for parsing.")

        file_payload = files[0]
        mime_type = file_payload.get("mimeType")

        if mime_type in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
            ocr_result = OcrTextParser().parse(
                {
                    **payload,
                    "parserMode": "OCR_TEXT",
                }
            )

            ocr_result["parserMode"] = self.parser_mode
            ocr_result["selectedParser"] = "OCR_TEXT"
            ocr_result["warnings"] = ocr_result.get("warnings", []) + [
                "AUTO selected OCR_TEXT because image files require OCR."
            ]

            return ocr_result

        if mime_type == "application/pdf":
            fast_result = FastTextParser().parse(
                {
                    **payload,
                    "parserMode": "FAST_TEXT",
                }
            )

            if should_use_fast_text(fast_result):
                fast_result["parserMode"] = self.parser_mode
                fast_result["selectedParser"] = "FAST_TEXT"
                fast_result["warnings"] = fast_result.get("warnings", []) + [
                    "AUTO selected FAST_TEXT because complete embedded PDF text was found."
                ]
                return fast_result

            ocr_result = OcrTextParser().parse(
                {
                    **payload,
                    "parserMode": "OCR_TEXT",
                }
            )

            ocr_result["parserMode"] = self.parser_mode
            ocr_result["selectedParser"] = "OCR_TEXT"
            ocr_result["warnings"] = ocr_result.get("warnings", []) + [
                "AUTO selected OCR_TEXT because embedded PDF text was weak, sparse, or template-like."
            ]

            return ocr_result

        raise ValueError(
            "AUTO currently supports PDF, PNG, JPG, JPEG, and WebP files."
        )
