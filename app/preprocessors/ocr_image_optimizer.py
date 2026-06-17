from pathlib import Path

from PIL import Image, ImageOps

from app.core.config import get_ocr_max_side, normalize_ocr_quality_mode


def get_image_size(image):
    width, height = image.size
    return width, height


def calculate_resize_dimensions(width, height, max_side):
    largest_side = max(width, height)

    if largest_side <= max_side:
        return width, height, False

    scale = max_side / largest_side

    return int(width * scale), int(height * scale), True


def optimize_image_for_ocr(image_path, quality_mode="BALANCED"):
    normalized_quality_mode = normalize_ocr_quality_mode(quality_mode)
    max_side = get_ocr_max_side(normalized_quality_mode)

    source_path = Path(image_path)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")

        original_width, original_height = get_image_size(image)

        new_width, new_height, was_resized = calculate_resize_dimensions(
            original_width,
            original_height,
            max_side,
        )

        if was_resized:
            image = image.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS,
            )

        optimized_path = source_path.with_name(
            f"{source_path.stem}_ocr_{normalized_quality_mode.lower()}.png"
        )

        image.save(optimized_path, format="PNG", optimize=True)

    return {
        "imagePath": str(optimized_path),
        "qualityMode": normalized_quality_mode,
        "maxSide": max_side,
        "originalSize": {
            "width": original_width,
            "height": original_height,
        },
        "optimizedSize": {
            "width": new_width,
            "height": new_height,
        },
        "wasResized": was_resized,
    }
