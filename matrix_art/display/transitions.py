from __future__ import annotations

import random
from typing import Callable, Iterator

from PIL import Image

TRANSITION_EFFECTS = [
    "none",
    "fade",
    "wipe-left",
    "wipe-right",
    "wipe-up",
    "wipe-down",
    "slide-left",
    "slide-right",
    "slide-up",
    "slide-down",
    "dissolve",
    "checkerboard",
    "random",
]

_RANDOM_POOL = [effect for effect in TRANSITION_EFFECTS if effect not in {"none", "random"}]


def normalize_transition_name(name: str | None) -> str:
    value = (name or "none").strip().lower()
    return value if value in TRANSITION_EFFECTS else "fade"


def _steps(duration_ms: int, fps: int) -> int:
    duration = max(0, min(10000, int(duration_ms or 0)))
    rate = max(1, min(120, int(fps or 1)))
    if duration <= 0:
        return 1
    return max(1, min(240, round((duration / 1000.0) * rate)))


def _rgb(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = image.convert("RGB")
    if img.size != size:
        img = img.resize(size, Image.Resampling.NEAREST)
    return img


def _ease_smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


def _wipe(old: Image.Image, new: Image.Image, direction: str, t: float) -> Image.Image:
    w, h = new.size
    out = old.copy()
    if direction == "wipe-left":
        amount = int(round(w * t))
        if amount > 0:
            out.paste(new.crop((0, 0, amount, h)), (0, 0))
    elif direction == "wipe-right":
        amount = int(round(w * t))
        if amount > 0:
            out.paste(new.crop((w - amount, 0, w, h)), (w - amount, 0))
    elif direction == "wipe-up":
        amount = int(round(h * t))
        if amount > 0:
            out.paste(new.crop((0, 0, w, amount)), (0, 0))
    else:  # wipe-down
        amount = int(round(h * t))
        if amount > 0:
            out.paste(new.crop((0, h - amount, w, h)), (0, h - amount))
    return out


def _slide(old: Image.Image, new: Image.Image, direction: str, t: float) -> Image.Image:
    w, h = new.size
    out = Image.new("RGB", (w, h), (0, 0, 0))
    if direction == "slide-left":
        offset = int(round(w * t))
        out.paste(old, (-offset, 0))
        out.paste(new, (w - offset, 0))
    elif direction == "slide-right":
        offset = int(round(w * t))
        out.paste(old, (offset, 0))
        out.paste(new, (offset - w, 0))
    elif direction == "slide-up":
        offset = int(round(h * t))
        out.paste(old, (0, -offset))
        out.paste(new, (0, h - offset))
    else:  # slide-down
        offset = int(round(h * t))
        out.paste(old, (0, offset))
        out.paste(new, (0, offset - h))
    return out


def _dissolve(old: Image.Image, new: Image.Image, t: float, order: list[int]) -> Image.Image:
    w, h = new.size
    out = old.copy()
    old_px = out.load()
    new_px = new.load()
    count = int(round(len(order) * t))
    for idx in order[:count]:
        x = idx % w
        y = idx // w
        old_px[x, y] = new_px[x, y]
    return out


def _checkerboard(old: Image.Image, new: Image.Image, t: float) -> Image.Image:
    w, h = new.size
    out = old.copy()
    old_px = out.load()
    new_px = new.load()
    # Reveal in a pixel-grid aware pattern. At t=1 everything is new.
    threshold = int(round(t * 16))
    for y in range(h):
        for x in range(w):
            phase = ((x & 3) + (y & 3))
            if threshold >= 16 or phase <= threshold // 2 or ((x + y) & 1 and threshold > 7):
                old_px[x, y] = new_px[x, y]
    return out


def _renderer_for(name: str, old: Image.Image, new: Image.Image, order: list[int] | None) -> Callable[[float], Image.Image]:
    def render(t: float) -> Image.Image:
        if name == "fade":
            return Image.blend(old, new, t)
        if name.startswith("wipe-"):
            return _wipe(old, new, name, t)
        if name.startswith("slide-"):
            return _slide(old, new, name, t)
        if name == "dissolve":
            assert order is not None
            return _dissolve(old, new, t, order)
        if name == "checkerboard":
            return _checkerboard(old, new, t)
        return Image.blend(old, new, t)

    return render


def iter_transition_frames(
    old_image: Image.Image,
    new_image: Image.Image,
    *,
    effect: str = "fade",
    duration_ms: int = 600,
    fps: int = 30,
    smoothing: bool = True,
    smoothing_strength: int = 35,
) -> Iterator[Image.Image]:
    """Yield panel-ready RGB transition frames from old_image to new_image.

    Smoothing applies a small smoothstep easing curve and temporal persistence between
    generated frames. At 64x64 this gives slide/wipe/dissolve effects a softer,
    less steppy feel while still ending on the exact target image.
    """
    size = new_image.size
    old = _rgb(old_image, size)
    new = _rgb(new_image, size)
    name = normalize_transition_name(effect)
    if name == "random":
        name = random.choice(_RANDOM_POOL)
    if name == "none":
        yield new
        return

    steps = _steps(duration_ms, fps)
    order: list[int] | None = None
    if name == "dissolve":
        order = list(range(size[0] * size[1]))
        random.shuffle(order)

    render = _renderer_for(name, old, new, order)
    use_smoothing = bool(smoothing) and steps > 2 and name != "fade"
    strength = max(0, min(100, int(smoothing_strength or 0)))
    # Keep the current raw frame dominant so motion stays clear on a low-res panel.
    persistence = 0.0 if not use_smoothing else min(0.65, strength / 100.0 * 0.65)
    previous_out: Image.Image | None = None

    for step in range(1, steps + 1):
        t = step / steps
        t_render = _ease_smoothstep(t) if use_smoothing else t
        frame = render(t_render)
        if use_smoothing and previous_out is not None and step < steps and persistence > 0:
            frame = Image.blend(previous_out, frame, 1.0 - persistence)
        previous_out = frame
        yield frame


def iter_transition_frames_dynamic(
    old_image: Image.Image,
    new_image: Image.Image,
    *,
    old_getter: Callable[[], Image.Image | None] | None = None,
    new_getter: Callable[[], Image.Image | None] | None = None,
    effect: str = "fade",
    duration_ms: int = 600,
    fps: int = 30,
    smoothing: bool = True,
    smoothing_strength: int = 35,
) -> Iterator[Image.Image]:
    """Yield transition frames while optionally sampling live old/new frames.

    This is used when leaving or entering animated sources. The transition shape
    still progresses from 0 to 1, but the old side and/or new side can be a
    changing frame source, so GIF and Code animations keep moving during the
    transition instead of freezing on one sampled frame.
    """
    size = new_image.size
    old_base = _rgb(old_image, size)
    new_base = _rgb(new_image, size)
    name = normalize_transition_name(effect)
    if name == "random":
        name = random.choice(_RANDOM_POOL)
    if name == "none":
        latest_new = new_getter() if new_getter else None
        yield _rgb(latest_new, size) if latest_new is not None else new_base
        return

    steps = _steps(duration_ms, fps)
    order: list[int] | None = None
    if name == "dissolve":
        order = list(range(size[0] * size[1]))
        random.shuffle(order)

    use_smoothing = bool(smoothing) and steps > 2 and name != "fade"
    strength = max(0, min(100, int(smoothing_strength or 0)))
    persistence = 0.0 if not use_smoothing else min(0.65, strength / 100.0 * 0.65)
    previous_out: Image.Image | None = None

    for step in range(1, steps + 1):
        t = step / steps
        t_render = _ease_smoothstep(t) if use_smoothing else t
        latest_old = old_getter() if old_getter else None
        latest_new = new_getter() if new_getter else None
        old = _rgb(latest_old, size) if latest_old is not None else old_base
        new = _rgb(latest_new, size) if latest_new is not None else new_base
        render = _renderer_for(name, old, new, order)
        frame = render(t_render)
        if use_smoothing and previous_out is not None and step < steps and persistence > 0:
            frame = Image.blend(previous_out, frame, 1.0 - persistence)
        previous_out = frame
        yield frame
