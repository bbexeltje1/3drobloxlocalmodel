from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class BackgroundRemovalError(RuntimeError):
    pass


def configured_model_dir() -> Path:
    return Path(os.getenv("FEYNOBG_MODEL_DIR", r"C:\Users\MB\FeyNobg")).expanduser()


def configured_python() -> str:
    return os.getenv("FEYNOBG_PYTHON", sys.executable)


def _worker_environment(model_dir: Path) -> dict[str, str]:
    allowed = ("PATH", "SystemRoot", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "HOME",
               "CUDA_PATH", "CUDA_HOME", "CUDA_VISIBLE_DEVICES", "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "TORCH_HOME",
               "PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONNOUSERSITE", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({"FEYNOBG_MODEL_DIR": str(model_dir), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    return env


def run_feynobg(source: Path, destination: Path, timeout: int = 300) -> None:
    model_dir = configured_model_dir()
    required = (model_dir / "model.safetensors", model_dir / "config.json", model_dir / "preprocessor_config.json")
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise BackgroundRemovalError("FeyNobg local files are missing: " + ", ".join(missing))
    worker = Path(__file__).with_name("feynobg_worker.py")
    env = _worker_environment(model_dir)
    cmd = [configured_python(), str(worker), str(source), str(destination)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackgroundRemovalError(f"FeyNobg worker could not run: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "No worker output").strip()[-3000:]
        raise BackgroundRemovalError(f"FeyNobg inference failed (exit {result.returncode}): {detail}")
    if not destination.is_file():
        raise BackgroundRemovalError("FeyNobg worker exited successfully but did not produce the expected PNG.")


def local_status() -> dict:
    model_dir = configured_model_dir()
    python = configured_python()
    files = {name: (model_dir / name).is_file() for name in ("model.safetensors", "config.json", "preprocessor_config.json")}
    package_ready, package_error = False, None
    if Path(python).is_file() or (not Path(python).parent.exists() and python == sys.executable):
        try:
            probe = subprocess.run(
                [python, "-c", "from PIL import Image; import torch; from nobg import AutoModel, AutoProcessor; print(torch.__version__)"],
                capture_output=True, text=True, timeout=12, check=False, env=_worker_environment(model_dir),
            )
            package_ready = probe.returncode == 0
            if not package_ready:
                package_error = (probe.stderr or probe.stdout)[-1200:]
        except Exception as exc:
            package_error = str(exc)
    else:
        package_error = f"Configured worker interpreter was not found: {python}"
    return {"model_dir": str(model_dir), "files": files, "package_ready": package_ready,
            "package_error": package_error, "ready": all(files.values()) and package_ready,
            "python": python}
