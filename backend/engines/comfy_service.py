"""Start the local ComfyUI server on demand for RoForge generation."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Callable, Dict, Any

from .comfy_pixal3d import check_comfyui_status


_START_LOCK = threading.Lock()


def _is_roforge_local_endpoint(comfy_url: str) -> bool:
    parsed = urlparse(comfy_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port in {None, 8188}


def _launch_comfyui(repo_root: Path) -> None:
    if os.name == "nt":
        launcher = repo_root / "scripts" / "start_comfyui_6gb.bat"
        if not launcher.is_file():
            raise RuntimeError(f"ComfyUI launcher not found: {launcher}")
        # Give ComfyUI its own visible console so startup errors are readable.
        subprocess.Popen(
            ["cmd.exe", "/k", "call", str(launcher)],
            cwd=str(repo_root),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    else:
        launcher = repo_root / "scripts" / "start_comfyui_6gb.sh"
        if not launcher.is_file():
            raise RuntimeError(f"ComfyUI launcher not found: {launcher}")
        subprocess.Popen(["bash", str(launcher)], cwd=str(repo_root))


def ensure_comfyui_ready(
    comfy_url: str,
    repo_root: Path,
    *,
    status_check: Callable[..., Dict[str, Any]] = check_comfyui_status,
    startup_timeout_sec: int = 300,
    poll_interval_sec: float = 2.0,
) -> Dict[str, Any]:
    """Return ComfyUI status, launching RoForge's local server if it is not already up."""
    status = status_check(comfy_url=comfy_url)
    if status.get("online") or not _is_roforge_local_endpoint(comfy_url):
        return status

    with _START_LOCK:
        # A second generation request may have arrived while the first waited for startup.
        status = status_check(comfy_url=comfy_url)
        if status.get("online"):
            return status
        _launch_comfyui(repo_root)

        deadline = time.monotonic() + startup_timeout_sec
        while time.monotonic() < deadline:
            time.sleep(poll_interval_sec)
            status = status_check(comfy_url=comfy_url)
            if status.get("online"):
                return status

    raise RuntimeError(
        f"RoForge started ComfyUI, but it did not become ready at {comfy_url} "
        f"within {startup_timeout_sec // 60} minutes. Check the ComfyUI console for startup errors."
    )
