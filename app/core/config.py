import os


APP_NAME = "FinFile Document Engine"
APP_VERSION = "0.2.0"

PARSER_PREVIEW_LIMIT = int(os.getenv("PARSER_PREVIEW_LIMIT", "50"))
MAX_SYNC_PARSE_PAGES = int(os.getenv("MAX_SYNC_PARSE_PAGES", "10"))
MAX_SYNC_PARSE_BYTES = int(os.getenv("MAX_SYNC_PARSE_BYTES", str(25 * 1024 * 1024)))

DEFAULT_OCR_LANGUAGE = os.getenv("DEFAULT_OCR_LANGUAGE", "en")