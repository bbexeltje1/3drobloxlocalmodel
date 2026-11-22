"""Offline-only Budget3D auxiliary-weight preflight. Never downloads or initializes GPU models."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) > 1:
        sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
    report = {"torch": False, "budget3d_imports": False, "idol_weights": None,
              "idol_files": {}, "dinov3_dir": None, "dinov3_ready": False,
              "flux2_repo": None, "flux2_cached": False, "errors": []}
    try:
        import torch
        report["torch"] = True
        from budget3d.models.load import idol_weights_dir
        from budget3d.sampling.sampler import ImagePreprocessor
        from budget3d.models.encoders import DINOV3_DIR, FLUX2_VAE_REPO
        report["budget3d_imports"] = ImagePreprocessor is not None
        idol_dir = Path(idol_weights_dir()).expanduser().resolve()
        required = ("config.json", "denoiser.safetensors", "decoder.safetensors", "decoder_gs.safetensors", "birefnet.safetensors")
        report["idol_weights"] = str(idol_dir)
        report["idol_files"] = {name: (idol_dir / name).is_file() for name in required}
        dino_dir = Path(DINOV3_DIR).expanduser()
        report["dinov3_dir"] = str(dino_dir)
        report["dinov3_ready"] = dino_dir.is_dir() and any(dino_dir.iterdir())
        report["flux2_repo"] = FLUX2_VAE_REPO
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(repo_id=FLUX2_VAE_REPO, local_files_only=True)
            report["flux2_cached"] = True
        except Exception as exc:
            report["errors"].append(f"FLUX.2 VAE is not available in the local HF cache: {exc}")
    except Exception as exc:
        report["errors"].append(f"Budget3D auxiliary preflight failed: {type(exc).__name__}: {exc}")
    report["ready"] = (report["torch"] and report["budget3d_imports"] and
                        all(report["idol_files"].values()) and report["dinov3_ready"] and report["flux2_cached"])
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
