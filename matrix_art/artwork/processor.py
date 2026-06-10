from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageColor, ImageSequence


RESAMPLE_MAP = {
    "nearest": Image.Resampling.NEAREST,
    "pixel": Image.Resampling.NEAREST,
    "smooth": Image.Resampling.LANCZOS,
    "lanczos": Image.Resampling.LANCZOS,
    "bicubic": Image.Resampling.BICUBIC,
    "bilinear": Image.Resampling.BILINEAR,
}


def parse_color(value: str, default: tuple[int, int, int] = (0, 0, 0)) -> tuple[int, int, int]:
    try:
        r, g, b = ImageColor.getrgb(value)[:3]
        return int(r), int(g), int(b)
    except Exception:
        return default


def resample_filter(name: str) -> Image.Resampling:
    return RESAMPLE_MAP.get(str(name).lower().strip(), Image.Resampling.NEAREST)


def process_image_file(
    path: Path,
    target_size: tuple[int, int] = (64, 64),
    scale_mode: str = "fit",
    resample: str = "nearest",
    background_color: str = "#000000",
) -> Image.Image:
    """Load an image and return one RGB frame ready for the panel."""
    with Image.open(path) as img:
        img.load()
        frame = process_image(img, target_size, scale_mode, resample, background_color)
    return frame


def process_image(
    img: Image.Image,
    target_size: tuple[int, int] = (64, 64),
    scale_mode: str = "fit",
    resample: str = "nearest",
    background_color: str = "#000000",
) -> Image.Image:
    target_w, target_h = target_size
    mode = str(scale_mode).lower().strip()
    filt = resample_filter(resample)
    bg = parse_color(background_color)

    if img.mode not in {"RGB", "RGBA"}:
        img = img.convert("RGBA")
    else:
        img = img.copy()

    if mode == "stretch":
        resized = img.resize((target_w, target_h), filt)
        return _flatten_to_rgb(resized, bg)

    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", (target_w, target_h), bg)

    if mode == "fill":
        scale = max(target_w / src_w, target_h / src_h)
    else:
        scale = min(target_w / src_w, target_h / src_h)

    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = img.resize((new_w, new_h), filt)

    if mode == "fill":
        left = max(0, (new_w - target_w) // 2)
        top = max(0, (new_h - target_h) // 2)
        cropped = resized.crop((left, top, left + target_w, top + target_h))
        return _flatten_to_rgb(cropped, bg)

    canvas = Image.new("RGBA", (target_w, target_h), bg + (255,))
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    canvas.alpha_composite(resized.convert("RGBA"), (x, y))
    return canvas.convert("RGB")



def process_scaled_image(
    img: Image.Image,
    transform_scale: float,
    offset_x: float,
    offset_y: float,
    target_size: tuple[int, int] = (64, 64),
    resample: str = "nearest",
    background_color: str = "#000000",
) -> Image.Image:
    """Scale and position a source image onto the panel canvas.

    ``transform_scale`` is measured in destination pixels per source pixel.
    ``offset_x`` and ``offset_y`` are the destination top-left position in the
    target canvas. This matches the browser upload editor so still images and
    GIF frames can share the same Scale mode behavior.
    """
    target_w, target_h = target_size
    bg = parse_color(background_color)
    if img.mode not in {"RGB", "RGBA"}:
        src = img.convert("RGBA")
    else:
        src = img.copy()

    src_w, src_h = src.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", target_size, bg)

    scale = max(0.0001, float(transform_scale or 0.0001))
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = src.resize((new_w, new_h), resample_filter(resample)).convert("RGBA")

    canvas = Image.new("RGBA", (target_w, target_h), bg + (255,))
    canvas.paste(resized, (int(round(offset_x)), int(round(offset_y))), resized)
    return canvas.convert("RGB")

def process_cropped_image(
    img: Image.Image,
    crop_x: float,
    crop_y: float,
    crop_w: float,
    crop_h: float,
    target_size: tuple[int, int] = (64, 64),
    resample: str = "nearest",
    background_color: str = "#000000",
) -> Image.Image:
    """Crop in source-image coordinates and scale the crop to the panel size."""
    bg = parse_color(background_color)
    if img.mode not in {"RGB", "RGBA"}:
        src = img.convert("RGBA")
    else:
        src = img.copy()

    src_w, src_h = src.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", target_size, bg)

    x = max(0.0, min(float(crop_x), float(src_w - 1)))
    y = max(0.0, min(float(crop_y), float(src_h - 1)))
    w = max(1.0, min(float(crop_w), float(src_w) - x))
    h = max(1.0, min(float(crop_h), float(src_h) - y))

    left = int(round(x))
    top = int(round(y))
    right = max(left + 1, int(round(x + w)))
    bottom = max(top + 1, int(round(y + h)))
    right = min(right, src_w)
    bottom = min(bottom, src_h)

    cropped = src.crop((left, top, right, bottom))
    resized = cropped.resize(target_size, resample_filter(resample))
    return _flatten_to_rgb(resized, bg)


def process_gif_bytes(
    data: bytes,
    target_size: tuple[int, int] = (64, 64),
    scale_mode: str = "fit",
    resample: str = "nearest",
    background_color: str = "#000000",
    *,
    crop_x: float | None = None,
    crop_y: float | None = None,
    crop_size: float | None = None,
    transform_scale: float | None = None,
    offset_x: float | None = None,
    offset_y: float | None = None,
    max_frames: int = 240,
    default_duration_ms: int = 100,
    min_duration_ms: int = 20,
    max_duration_ms: int = 5000,
) -> list[tuple[Image.Image, int]]:
    """Decode an animated GIF into panel-ready RGB frames.

    Returns a list of (image, duration_ms). The original GIF is not stored by
    this helper. Extremely short or missing frame delays are clamped so playback
    is visible and does not busy-loop the display worker. The crop mode uses
    source-image coordinates so browser preview, panel preview, and save can all
    share the same crop/zoom settings.
    """
    frames: list[tuple[Image.Image, int]] = []
    mode = str(scale_mode).lower().strip()
    with Image.open(BytesIO(data)) as img:
        for index, frame in enumerate(ImageSequence.Iterator(img)):
            if index >= max(1, int(max_frames)):
                break
            duration = int(frame.info.get("duration") or img.info.get("duration") or default_duration_ms)
            duration = max(int(min_duration_ms), min(int(max_duration_ms), duration))
            rgba = frame.convert("RGBA")
            if mode == "scale" and transform_scale is not None:
                processed = process_scaled_image(
                    rgba,
                    transform_scale=transform_scale,
                    offset_x=offset_x or 0,
                    offset_y=offset_y or 0,
                    target_size=target_size,
                    resample=resample,
                    background_color=background_color,
                )
            elif mode == "crop" and crop_size is not None:
                processed = process_cropped_image(
                    rgba,
                    crop_x or 0,
                    crop_y or 0,
                    crop_size,
                    crop_size,
                    target_size=target_size,
                    resample=resample,
                    background_color=background_color,
                )
            else:
                processed = process_image(
                    rgba,
                    target_size=target_size,
                    scale_mode=scale_mode,
                    resample=resample,
                    background_color=background_color,
                )
            frames.append((processed, duration))
    return frames


def image_to_png_bytes(img: Image.Image) -> bytes:
    out = BytesIO()
    img.save(out, format="PNG", optimize=False)
    return out.getvalue()


def png_bytes_to_image(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as img:
        img.load()
        return img.convert("RGB")


def _flatten_to_rgb(img: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    if img.mode == "RGB":
        return img.copy()
    rgba = img.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, bg + (255,))
    canvas.alpha_composite(rgba)
    return canvas.convert("RGB")
