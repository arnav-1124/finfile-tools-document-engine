import re


MIN_TABLE_ROWS = 2
MIN_TABLE_COLUMNS = 2


def split_line_into_cells(line):
    """
    Basic OCR table splitter.

    It handles:
    - tabs
    - repeated spaces
    - pipe-separated OCR output
    - common table-like separators

    It intentionally does not split on single spaces because descriptions,
    names, addresses, and narration fields often contain normal spaces.
    """
    clean_line = str(line or "").strip()

    if not clean_line:
        return []

    if "|" in clean_line:
        parts = re.split(r"\s*\|\s*", clean_line)
    elif "\t" in clean_line:
        parts = re.split(r"\t+", clean_line)
    else:
        parts = re.split(r"\s{2,}", clean_line)

    cells = [part.strip() for part in parts if part.strip()]

    return cells


def normalize_table_rows(rows):
    if not rows:
        return [], []

    max_columns = max(len(row) for row in rows)

    normalized_rows = []
    for row in rows:
        normalized_rows.append(row + [""] * (max_columns - len(row)))

    columns = [f"Column {index + 1}" for index in range(max_columns)]

    return columns, normalized_rows


def calculate_table_score(candidate_rows):
    if not candidate_rows:
        return 0

    multi_column_rows = [row for row in candidate_rows if len(row) >= MIN_TABLE_COLUMNS]

    if len(multi_column_rows) < MIN_TABLE_ROWS:
        return 0

    column_counts = [len(row) for row in multi_column_rows]
    most_common_column_count = max(set(column_counts), key=column_counts.count)

    consistent_rows = [
        row for row in multi_column_rows if len(row) == most_common_column_count
    ]

    consistency_ratio = len(consistent_rows) / max(len(multi_column_rows), 1)
    coverage_ratio = len(multi_column_rows) / max(len(candidate_rows), 1)

    score = round((consistency_ratio * 0.6) + (coverage_ratio * 0.4), 2)

    return score


def reconstruct_table_from_ocr_lines(lines):
    candidate_rows = []

    for line in lines:
        cells = split_line_into_cells(line)

        if cells:
            candidate_rows.append(cells)

    table_score = calculate_table_score(candidate_rows)

    if table_score < 0.45:
        return {
            "isTableLike": False,
            "columns": ["Extracted text"],
            "rows": [[line] for line in lines if str(line).strip()],
            "score": table_score,
            "warnings": [
                "OCR output did not look structured enough for table reconstruction. Returning text lines instead."
            ],
        }

    table_rows = [row for row in candidate_rows if len(row) >= MIN_TABLE_COLUMNS]
    columns, normalized_rows = normalize_table_rows(table_rows)

    return {
        "isTableLike": True,
        "columns": columns,
        "rows": normalized_rows,
        "score": table_score,
        "warnings": [
            f"Baseline OCR table reconstruction applied with score {table_score}."
        ],
    }