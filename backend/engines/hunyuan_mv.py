"""Direct Python Low-VRAM Runner for Tencent Hunyuan3D-2mv (`tencent/Hunyuan3D-2mv`).
Uses `hunyuan3d-dit-v2-mv-turbo` (1.1B) in FP16 with octree_resolution=256 (~4.5–5.5 GB VRAM),
then immediately frees GPU memory so camera-projected PBR UV baking runs with 0 extra VRAM.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Dict

from PIL import Image
import trimesh


def is_hunyuan_available() -> bool:
    try:
        import torch  # noqa: F401
        import hy3dgen.shapegen  # noqa: F401
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def run_hunyuan3d_2mv_lowvram(
    view_paths: Dict[str, Path],
    seed: int = 42,
    octree_resolution: int = 256,
    steps: int = 8,
) -> trimesh.Trimesh:
    """Generate watertight 3D mesh from 2–4 views in ~4.5–5.5 GB VRAM using Hunyuan3D-2mv-Turbo."""
    import torch
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        "tencent/Hunyuan3D-2mv",
        subfolder="hunyuan3d-dit-v2-mv-turbo",
        use_safetensors=True,
        torch_dtype=torch.float16,
        device="cuda",
    )
    try:
        pipeline.enable_flashvdm()
    except Exception:
        pass

    view_payload = {}
    for k in ("front", "left", "back", "right"):
        if k in view_paths:
            view_payload[k] = Image.open(view_paths[k]).convert("RGBA")

    mesh = pipeline(
        image=view_payload,
        num_inference_steps=int(steps),
        octree_resolution=int(octree_resolution),
        num_chunks=8000,
        generator=torch.manual_seed(int(seed)),
        output_type="trimesh",
    )[0]

    # Immediately offload & clear VRAM for 6 GB cards
    del pipeline
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return mesh
