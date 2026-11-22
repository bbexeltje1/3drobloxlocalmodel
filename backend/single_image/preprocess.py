from __future__ import annotations

from pathlib import Path
from PIL import Image


class ImagePreparationError(RuntimeError):
    pass


def prepare_for_idol(source: Path, destination: Path, background: tuple[int, int, int] = (255, 255, 255)) -> dict:
    """Preserve the full source frame; leave framing/resizing/cropping to Idol's own preprocessor.

    Budget3D's official ImagePreprocessor is invoked by its sampling entry point. This adapter only
    normalizes mode for that API and composites alpha on a neutral, explicit background without
    cropping or changing the source aspect ratio.
    """
    try:
        with Image.open(source) as im:
            rgba = im.convert("RGBA")
            size = rgba.size
            bg = Image.new("RGBA", size, (*background, 255))
            bg.alpha_composite(rgba)
            destination.parent.mkdir(parents=True, exist_ok=True)
            bg.convert("RGB").save(destination, format="PNG")
    except Exception as exc:
        raise ImagePreparationError(f"Could not prepare image for Idol: {exc}") from exc
    return {"width": size[0], "height": size[1], "aspect_ratio": round(size[0] / size[1], 6),
            "framing": "full original frame; official Idol ImagePreprocessor handles model framing"}
