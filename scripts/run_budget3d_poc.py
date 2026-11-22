#!/usr/bin/env python3
"""Run Budget3D-Idol-Turbo locally from one image; outputs a Gaussian-splat PLY."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="Input PNG or JPG")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs") / "budget3d_poc.ply",
        help="Output Gaussian-splat PLY (default: outputs/budget3d_poc.ply)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--budget",
        type=float,
        default=0.0625,
        help="Turbo token budget; 0.0625 is the minimum preset for a 6 GB GPU",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("BUDGET3D_HOME", Path.home() / "Budget3D")),
        help="Existing Budget3D checkout (default: %%USERPROFILE%%/Budget3D)",
    )
    args = parser.parse_args()

    home = args.home.expanduser().resolve()
    image = args.image.expanduser().resolve()
    output = args.out.expanduser().resolve()
    python = home / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    checkpoint = home / "weights" / "budget3d_idol_turbo.safetensors"
    sample_script = home / "scripts" / "sample.py"
    idol_sdk = home / "third_party" / "idol-sdk"
    dinov3 = home / "weights" / "dinov3" / "vith16plus_lvd1689m"

    missing = [p for p in (image, python, checkpoint, sample_script, idol_sdk / "idol", dinov3) if not p.exists()]
    if missing:
        print("Missing local input/install files:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 2
    if output.suffix.lower() != ".ply":
        parser.error("--out must end in .ply")

    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(python),
        str(sample_script),
        "--ckpt",
        str(checkpoint),
        "--turbo",
        "--fast",
        "--image",
        str(image),
        "--budget",
        str(args.budget),
        "--mode",
        "synthetic",
        "--seed",
        str(args.seed),
        "--num_gaussians",
        "65536",
        "--out",
        str(output),
    ]
    env = os.environ.copy()
    env["IDOL_ROOT"] = str(idol_sdk)
    env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    print("Running local Budget3D-Idol-Turbo (no ComfyUI server or browser required).", flush=True)
    print("This produces a Gaussian-splat PLY, not a Roblox triangle mesh.", flush=True)
    try:
        result = subprocess.run(command, cwd=home, env=env, check=False)
    except OSError as exc:
        print(f"Could not launch Budget3D: {exc}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(f"Budget3D exited with code {result.returncode}.", file=sys.stderr)
        return result.returncode or 1
    if not output.is_file() or output.stat().st_size == 0:
        print(f"Budget3D did not create an output PLY at {output}.", file=sys.stderr)
        return 1
    print(f"Saved PLY: {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
