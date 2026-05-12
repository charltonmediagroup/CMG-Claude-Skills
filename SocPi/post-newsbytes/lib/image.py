"""Image utilities — resize a Drive-hosted image to Instagram's 1080×1080
square, padded with white so we never crop the subject.

Pillow handles the heavy lifting. Output is JPEG (regardless of input
format) since IG accepts JPEG and we don't want to ship transparent PNGs
through the SocialPilot pipeline.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

IG_SIZE = (1080, 1080)
IG_BG = (255, 255, 255)


def resize_for_instagram(src: Path) -> Path:
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"image not found: {src}")
    out = src.with_name(f"{src.stem}-ig.jpg")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail(IG_SIZE, Image.LANCZOS)
        canvas = Image.new("RGB", IG_SIZE, IG_BG)
        x = (IG_SIZE[0] - im.width) // 2
        y = (IG_SIZE[1] - im.height) // 2
        canvas.paste(im, (x, y))
        canvas.save(out, format="JPEG", quality=92, optimize=True)
    return out
