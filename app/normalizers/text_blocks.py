def create_text_block(
    text,
    page_number=1,
    confidence=None,
    bbox=None,
    block_type="text",
):
    return {
        "type": block_type,
        "pageNumber": page_number,
        "text": text,
        "confidence": confidence,
        "bbox": bbox,
    }


def normalize_text_lines(lines, page_number=1):
    normalized_blocks = []

    for line in lines or []:
        if isinstance(line, str):
            text = line.strip()

            if text:
                normalized_blocks.append(
                    create_text_block(
                        text=text,
                        page_number=page_number,
                    )
                )

        elif isinstance(line, dict):
            text = str(line.get("text") or "").strip()

            if text:
                normalized_blocks.append(
                    create_text_block(
                        text=text,
                        page_number=line.get("pageNumber") or page_number,
                        confidence=line.get("confidence"),
                        bbox=line.get("bbox"),
                        block_type=line.get("type") or "text",
                    )
                )

    return normalized_blocks
