"""Optional single-image Budget3D-Idol-Turbo runner.

The upstream model runs in its own Python environment and emits a Gaussian-splat PLY,
not a triangle mesh. It is deliberately kept separate from the Roblox mesh pipeline.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _budget3d_home() -> Path:
    configured = os.environ.get("BUDGET3D_HOME")
    return Path(configured).expanduser() if configured else Path.home() / "Budget3D"


def _budget3d_python(home: Path) -> Path:
    configured = os.environ.get("BUDGET3D_PYTHON")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return home / ".venv" / "Scripts" / "python.exe"
    return home / ".venv" / "bin" / "python"


def run_budget3d_idol_turbo(
    image_path: Path,
    output_ply_path: Path,
    seed: int = 42,
    timeout_sec: int = 1800,
) -> Path:
    """Generate a Gaussian-splat .ply from exactly one image using local Budget3D-Turbo."""
    home = _budget3d_home().resolve()
    python = _budget3d_python(home).resolve()
    checkpoint = home / "weights" / "budget3d_idol_turbo.safetensors"
    sample_script = home / "scripts" / "sample.py"
    idol_sdk = home / "third_party" / "idol-sdk"
    dinov3 = home / "weights" / "dinov3" / "vith16plus_lvd1689m"

    missing = [
        str(path)
        for path in (python, checkpoint, sample_script, idol_sdk / "idol", dinov3)
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(
            "Budget3D-Idol-Turbo is not set up. Run scripts\\setup_budget3d_windows.bat, "
            "accept the DINOv3 and FLUX.2 model terms on Hugging Face, then follow the one-time "
            "DINOv3 conversion/login instructions printed by the setup script. Missing: "
            + ", ".join(missing)
        )

    output_ply_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(python),
        str(sample_script),
        "--ckpt",
        str(checkpoint),
        "--turbo",
        "--fast",
        "--image",
        str(image_path.resolve()),
        # Official model minimum (1/16 of the dense token layout); this is an
        # experimental attempt to stay within 6 GB, not a guaranteed fit.
        "--budget",
        "0.0625",
        "--mode",
        "synthetic",
        "--seed",
        str(int(seed)),
        "--num_gaussians",
        "65536",
        "--out",
        str(output_ply_path.resolve()),
    ]
    env = os.environ.copy()
    env["IDOL_ROOT"] = str(idol_sdk.resolve())
    env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    try:
        result = subprocess.run(
            command,
            cwd=str(home),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Budget3D-Turbo exceeded its {timeout_sec // 60}-minute timeout.") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start Budget3D-Turbo: {exc}") from exc

    if result.returncode != 0:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-28:]).strip()
        raise RuntimeError(
            "Budget3D-Turbo failed. Close ComfyUI and other GPU apps, verify the separate "
            "Budget3D setup and Hugging Face model access, then retry. On a 6 GB GTX 1660 SUPER "
            "the published low-budget peak is at the VRAM limit, so CUDA out-of-memory or an "
            "unsupported fast-attention/BF16 kernel is possible.\n\n"
            + (tail or f"Budget3D exited with code {result.returncode}.")
        )
    if not output_ply_path.is_file() or output_ply_path.stat().st_size == 0:
        raise RuntimeError("Budget3D exited successfully but did not create its Gaussian-splat PLY output.")
    return output_ply_path
