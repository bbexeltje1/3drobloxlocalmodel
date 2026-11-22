"""One-shot official NoBg/FeyNobg inference worker, isolated from the FastAPI process."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PIL import Image


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: feynobg_worker.py INPUT OUTPUT.png", file=sys.stderr)
        return 2
    model_dir = Path(os.environ["FEYNOBG_MODEL_DIR"]).resolve()
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        import torch
        from nobg import AutoModel, AutoProcessor
    except Exception as exc:
        print(f"Cannot import official nobg/PyTorch runtime in configured FeyNobg environment: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3
    try:
        model = AutoModel.from_pretrained(str(model_dir)).eval()
        processor = AutoProcessor.from_pretrained(str(model_dir))
        image = Image.open(source).convert("RGB")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
        inputs = processor(image, return_tensors="pt")
        if hasattr(inputs, "to"):
            inputs = inputs.to(device)
        else:
            inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
        with torch.inference_mode():
            outputs = model(pixel_values=inputs["pixel_values"])
        alpha = processor.post_process_alpha_matting(outputs, target_sizes=[(image.height, image.width)])[0]
        cutout = processor.cutout(image, alpha).convert("RGBA")
        if cutout.size != image.size:
            raise RuntimeError(f"Cutout dimensions changed unexpectedly: {cutout.size} != {image.size}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        cutout.save(destination, format="PNG")
        print(f"FeyNobg local inference complete on {device}: {cutout.width}x{cutout.height}")
    except Exception as exc:
        print(f"FeyNobg local inference error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    finally:
        if "torch" in locals() and torch.cuda.is_available():
            torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
