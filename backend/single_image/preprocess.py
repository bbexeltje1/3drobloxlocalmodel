from __future__ import annotations

from pathlib import Path
from PIL import Image


class ImagePreparationError(RuntimeError):
    pass


def prepare_for_idol(source: Path, destination: Path) -> dict:
    """Preserve full-frame RGBA; let Idol use the existing matte instead of rematting.

    The official Idol preprocessor detects non-opaque alpha and skips its own BiRefNet
    background-removal pass. Keeping FeyNobg's matte avoids discarding a good cutout and
    asking the second model to find the subject again. Opaque RGB sources still take Idol's
    official background-removal path.
    """
    try:
        with Image.open(source) as im:
            rgba = im.convert("RGBA")
            size = rgba.size
            destination.parent.mkdir(parents=True, exist_ok=True)
            rgba.save(destination, format="PNG")
    except Exception as exc:
        raise ImagePreparationError(f"Could not prepare image for Idol: {exc}") from exc
    return {"width": size[0], "height": size[1], "aspect_ratio": round(size[0] / size[1], 6),
            "framing": "full original frame; official Idol ImagePreprocessor handles model framing"}
