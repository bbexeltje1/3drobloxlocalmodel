#!/usr/bin/env python3
"""Download the public Budget3D-Idol-Turbo model files and dependencies without login.

This mirrors the other RoForge model downloader: files already present are skipped,
and inference remains local after the one-time downloads.
"""
from __future__ import annotations

import argparse
from pathlib import Path


TURBO_REPO = "BudgetAny/Budget3D-Idol-Turbo"
IDOL_REPO = "speridlabs/idol"
FLUX_VAE_REPO = "black-forest-labs/FLUX.2-klein-4B"


def download_budget3d_models(budget3d_dir: Path) -> None:
    from huggingface_hub import hf_hub_download, snapshot_download

    home = budget3d_dir.expanduser().resolve()
    weights_dir = home / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    turbo_files = ("budget3d_idol_turbo.safetensors", "config.json")
    for name in turbo_files:
        target = weights_dir / name
        if target.is_file() and target.stat().st_size > 1_000_000:
            print(f"[Budget3D] Already present; skipping {target}")
            continue
        print(f"[Budget3D] Downloading public Turbo file: {name}")
        hf_hub_download(
            repo_id=TURBO_REPO,
            filename=name,
            local_dir=str(weights_dir),
        )

    print(f"[Budget3D] Caching public Idol decoder/denoiser files from {IDOL_REPO}...")
    snapshot_download(
        repo_id=IDOL_REPO,
        allow_patterns=["config.json", "*.safetensors"],
    )

    print(f"[Budget3D] Caching only the FLUX.2 Klein VAE files from {FLUX_VAE_REPO}...")
    snapshot_download(
        repo_id=FLUX_VAE_REPO,
        allow_patterns=["vae/config.json", "vae/*.json", "vae/*.safetensors"],
    )

    print("[Budget3D] Public model weights are cached. No Hugging Face login/token was used.")
    print("[Budget3D] Next, convert the public DINOv3 checkpoint with scripts/convert_dinov3_to_hf.py.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--budget3d-dir",
        type=Path,
        default=Path.home() / "Budget3D",
        help="Budget3D checkout directory (default: ~/Budget3D)",
    )
    args = parser.parse_args()
    download_budget3d_models(args.budget3d_dir)


if __name__ == "__main__":
    main()
