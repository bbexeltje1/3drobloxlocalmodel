#!/usr/bin/env python3
"""RoForge 3D — Hugging Face Model Downloader for 6 GB VRAM + 32 GB RAM PCs.

Verified exact Hugging Face repository paths (no auth token required):
  - Comfy-Org/Pixal3D  :: diffusion_models/pixal3d_multiview_int8_convrot.safetensors (5.20 GiB)
  - Comfy-Org/Pixal3D  :: clip_vision/dino_v3_L_naf_fp32.safetensors                  (1.13 GiB)
  - Comfy-Org/Pixal3D  :: vae/trellis_2_shape_vae_bf16.safetensors                    (1.02 GiB)
  - Comfy-Org/Pixal3D  :: vae/trellis_2_texture_vae_bf16.safetensors                  (0.88 GiB)
  - Comfy-Org/BiRefNet :: background_removal/birefnet.safetensors                     (0.41 GiB)
  - Idol (optional)   :: public Idol + TripoSplat encoder/decoder files for ComfyUI

Downloads directly into <ComfyUI>/models/<subfolder>/ without creating duplicate cache copies!

Usage:
  python scripts/download_models_6gb.py --profile pixal3d --comfy-dir "C:/ComfyUI"
  python scripts/download_models_6gb.py --profile pixal3d --gguf --comfy-dir "C:/ComfyUI"
  python scripts/download_models_6gb.py --profile hunyuan
  python scripts/download_models_6gb.py --profile idol --comfy-dir "C:/ComfyUI"
"""

from __future__ import annotations

import argparse
from pathlib import Path


def resolve_comfy_models_dir(comfy_dir: Path) -> Path:
    """Support both git-cloned ComfyUI (C:/ComfyUI/models) and Windows Portable (C:/ComfyUI_windows_portable/ComfyUI/models)."""
    if (comfy_dir / "ComfyUI" / "models").exists():
        return comfy_dir / "ComfyUI" / "models"
    return comfy_dir / "models"


def download_pixal3d(comfy_dir: Path, include_gguf: bool = False) -> None:
    from huggingface_hub import hf_hub_download, snapshot_download

    models_dir = resolve_comfy_models_dir(comfy_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Exact verified paths from Comfy-Org's official 3d_pixal3d_multi_views.json template
    # Because repo relative paths match ComfyUI's models/ subfolders (diffusion_models/, clip_vision/, vae/, background_removal/),
    # passing local_dir=models_dir writes directly to the exact target path with zero duplicate cache copies!
    targets = [
        ("Comfy-Org/Pixal3D", "diffusion_models/pixal3d_multiview_int8_convrot.safetensors", "5.20 GiB"),
        ("Comfy-Org/Pixal3D", "clip_vision/dino_v3_L_naf_fp32.safetensors", "1.13 GiB"),
        ("Comfy-Org/Pixal3D", "vae/trellis_2_shape_vae_bf16.safetensors", "1.02 GiB"),
        ("Comfy-Org/Pixal3D", "vae/trellis_2_texture_vae_bf16.safetensors", "0.88 GiB"),
        ("Comfy-Org/BiRefNet", "background_removal/birefnet.safetensors", "0.41 GiB"),
    ]

    print(f"[RoForge 3D] Downloading Pixal3D Multi-View 6 GB VRAM pack directly into: {models_dir}\n")
    for idx, (repo_id, rel_path, size_label) in enumerate(targets, start=1):
        dest = models_dir / rel_path
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"  [{idx}/{len(targets)}] [SKIP] Already exists: {dest}")
            continue

        print(f"  [{idx}/{len(targets)}] [GET ] {repo_id} :: {rel_path} ({size_label})")
        saved_path = hf_hub_download(
            repo_id=repo_id,
            filename=rel_path,
            local_dir=str(models_dir),
        )
        print(f"         [OK  ] Saved -> {saved_path}\n")

    if include_gguf:
        gguf_dir = models_dir / "Pixal3D-GGUF"
        gguf_dir.mkdir(parents=True, exist_ok=True)
        print("[RoForge 3D] Downloading Aero-Ex/Pixal3D-GGUF (Q4_K_M ultra-low VRAM ~748 MB/stage)...")
        snapshot_download(
            repo_id="Aero-Ex/Pixal3D-GGUF",
            allow_patterns=[
                "pipeline.json",
                "README.md",
                "Sparse/*Q4_K_M.gguf",
                "Sparse/*.json",
                "shape/*512*Q4_K_M.gguf",
                "shape/*512*.json",
                "texture/*Q4_K_M.gguf",
                "texture/*.json",
                "decoder/*",
            ],
            local_dir=str(gguf_dir),
        )
        print(f"  [OK  ] Saved GGUF pack -> {gguf_dir}\n")

    print("========================================================================")
    print("[SUCCESS] All 5 Pixal3D Multi-View models are installed!")
    print(f"  Models folder : {models_dir}")
    print("  Next step     : Run scripts\\start_comfyui_6gb.bat")
    print("========================================================================")


def download_comfyui_idol(comfy_dir: Path) -> None:
    """Install public ComfyUI-Idol model weights directly into ComfyUI's model folders."""
    from huggingface_hub import hf_hub_download

    models_dir = resolve_comfy_models_dir(comfy_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    targets = [
        ("nynxz/Idol", "diffusion_models/idol_fp16.safetensors", "0.74 GiB"),
        ("nynxz/Idol", "vae/idol_decoder_fp16.safetensors", "0.58 GiB"),
        ("VAST-AI/TripoSplat", "clip_vision/dino_v3_vit_h.safetensors", "1.68 GiB"),
        ("VAST-AI/TripoSplat", "vae/flux2-vae.safetensors", "0.34 GiB"),
        ("Comfy-Org/BiRefNet", "background_removal/birefnet.safetensors", "0.44 GiB"),
    ]

    print(f"[ComfyUI-Idol] Installing public model files in {models_dir}")
    for index, (repo_id, relative_path, size_label) in enumerate(targets, start=1):
        target = models_dir / relative_path
        if target.is_file() and target.stat().st_size > 1_000_000:
            print(f"  [{index}/{len(targets)}] [SKIP] Already present: {target}")
            continue
        print(f"  [{index}/{len(targets)}] [GET ] {repo_id} :: {relative_path} ({size_label})")
        saved_path = hf_hub_download(
            repo_id=repo_id,
            filename=relative_path,
            local_dir=str(models_dir),
        )
        print(f"         [OK  ] Saved -> {saved_path}")

    print("[ComfyUI-Idol] Public weights installed without Hugging Face login or token.")
    print("[ComfyUI-Idol] Close/restart ComfyUI to reload the custom nodes and model list.")


def download_hunyuan_2mv() -> None:
    from huggingface_hub import snapshot_download

    print("[RoForge 3D] Pre-caching tencent/Hunyuan3D-2mv (hunyuan3d-dit-v2-mv-turbo, ~4.7 GB)...")
    snapshot_download(
        repo_id="tencent/Hunyuan3D-2mv",
        allow_patterns=[
            "config.json",
            "hunyuan3d-dit-v2-mv-turbo/config.yaml",
            "hunyuan3d-dit-v2-mv-turbo/model.fp16.safetensors",
            "README.md",
            "LICENSE*",
        ],
    )
    print("[SUCCESS] Cached tencent/Hunyuan3D-2mv in local Hugging Face cache!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download 6 GB VRAM Multi-View 3D models from Hugging Face.")
    parser.add_argument("--profile", choices=["pixal3d", "hunyuan", "idol"], default="pixal3d")
    parser.add_argument("--comfy-dir", type=Path, default=Path("C:/ComfyUI"))
    parser.add_argument("--gguf", action="store_true", help="Also download Aero-Ex/Pixal3D-GGUF Q4_K_M weights")
    args = parser.parse_args()

    if args.profile == "pixal3d":
        download_pixal3d(args.comfy_dir.resolve(), include_gguf=args.gguf)
    elif args.profile == "idol":
        if args.gguf:
            parser.error("--gguf applies only to the pixal3d profile")
        download_comfyui_idol(args.comfy_dir.resolve())
    else:
        download_hunyuan_2mv()


if __name__ == "__main__":
    main()
