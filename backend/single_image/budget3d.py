from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Callable


class Budget3DError(RuntimeError):
    pass


def _offline_environment() -> dict[str, str]:
    allowed = ("PATH", "SystemRoot", "WINDIR", "USERPROFILE", "USERNAME", "USER", "LOGNAME", "LNAME",
               "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "HOME", "CUDA_PATH", "CUDA_HOME",
               "CUDA_VISIBLE_DEVICES", "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE",
               "TORCH_HOME", "BUDGET3D_DINOV3", "BUDGET3D_FLUX2_VAE")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    return env


def _configured_paths() -> tuple[Path, Path, str]:
    repo_value = os.getenv("BUDGET3D_REPO", "").strip()
    if not repo_value:
        raise Budget3DError("BUDGET3D_REPO is not configured. Set it to the existing official Budget3D checkout; no code or weights will be downloaded.")
    repo = Path(repo_value).expanduser()
    ckpt = Path(os.getenv("BUDGET3D_CHECKPOINT", r"C:\Users\MB\weights\budget3d_idol.safetensors")).expanduser()
    python = os.getenv("BUDGET3D_PYTHON", "") or str(repo / ".venv" / "Scripts" / "python.exe")
    if os.name != "nt" and not Path(python).exists():
        python = os.getenv("BUDGET3D_PYTHON", "") or str(repo / ".venv" / "bin" / "python")
    return repo, ckpt, python


def status() -> dict:
    try:
        repo, ckpt, python = _configured_paths()
        repo_ready = (repo / "scripts" / "sample.py").is_file()
        checkpoint_ready = ckpt.is_file()
        python_ready = Path(python).is_file()
        package_ready, auxiliary_ready, package_error, auxiliary = False, False, None, None
        if repo_ready and python_ready:
            env = _offline_environment()
            try:
                probe_script = Path(__file__).with_name("budget3d_preflight.py")
                probe = subprocess.run([python, str(probe_script), str(repo)], cwd=repo, env=env,
                                       capture_output=True, text=True, timeout=45, check=False)
                if probe.returncode == 0:
                    auxiliary = json.loads(probe.stdout.strip().splitlines()[-1])
                    package_ready = bool(auxiliary.get("torch") and auxiliary.get("budget3d_imports"))
                    auxiliary_ready = bool(auxiliary.get("ready"))
                    if auxiliary.get("errors"):
                        package_error = "; ".join(auxiliary["errors"])[-1600:]
                else:
                    package_error = (probe.stderr or probe.stdout)[-1600:]
            except Exception as exc:
                package_error = str(exc)
        ready = repo_ready and checkpoint_ready and python_ready and package_ready and auxiliary_ready
        return {"repo": str(repo), "repo_ready": repo_ready,
                "checkpoint": str(ckpt), "checkpoint_ready": checkpoint_ready, "python": python,
                "python_ready": python_ready, "package_ready": package_ready,
                "auxiliary_weights_ready": auxiliary_ready, "auxiliary": auxiliary,
                "package_error": package_error, "ready": ready,
                "minimum_budget": 0.0625, "cuda_checked": False}
    except Budget3DError as exc:
        return {"ready": False, "error": str(exc), "minimum_budget": 0.0625}


def generate(image: Path, output_ply: Path, budget: float, on_log: Callable[[str], None] | None = None,
             timeout: int = 3600) -> None:
    if not 0.0625 <= float(budget) <= 1.0:
        raise Budget3DError("Budget3D token budget must be between 0.0625 (lowest supported) and 1.0.")
    repo, checkpoint, python = _configured_paths()
    sample_script = repo / "scripts" / "sample.py"
    if not sample_script.is_file():
        raise Budget3DError(f"Official Budget3D inference script was not found at {sample_script}.")
    if not checkpoint.is_file():
        raise Budget3DError(f"Local Budget3D checkpoint was not found: {checkpoint}. No replacement was downloaded.")
    if not Path(python).is_file():
        raise Budget3DError(f"Budget3D isolated Python was not found: {python}. Set BUDGET3D_PYTHON to the existing environment interpreter.")

    # The official sampler selects CUDA when available and CPU otherwise. This integration
    # explicitly requires CUDA so it never silently turns a 6 GB GPU job into a CPU run.
    probe = [python, "-c", "import json, torch; print(json.dumps({'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'vram':round(torch.cuda.get_device_properties(0).total_memory/1024**3,2) if torch.cuda.is_available() else None}))"]
    try:
        check = subprocess.run(probe, cwd=repo, capture_output=True, text=True, timeout=45, check=False)
    except Exception as exc:
        raise Budget3DError(f"Could not probe CUDA in the Budget3D environment: {exc}") from exc
    if check.returncode:
        raise Budget3DError("Budget3D environment cannot import PyTorch for its CUDA check: " + (check.stderr or check.stdout)[-2000:])
    try:
        hardware = json.loads(check.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise Budget3DError(f"Budget3D CUDA probe returned invalid output: {check.stdout[-1000:]}") from exc
    if on_log:
        on_log(f"Budget3D preflight: CUDA={hardware.get('cuda')}, GPU={hardware.get('gpu')}, VRAM={hardware.get('vram')} GiB")
    if not hardware.get("cuda"):
        raise Budget3DError("Budget3D CUDA inference is unavailable in its configured Python environment. The official sampler would otherwise choose CPU; CPU fallback is disabled.")

    output_ply.parent.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).with_name("budget3d_worker.py")
    cmd = [python, "-u", str(worker), str(repo), str(checkpoint), str(image), str(output_ply),
           str(float(budget)), "42"]
    env = _offline_environment()
    env["PYTHONUNBUFFERED"] = "1"
    # Budget3D's public sample.py currently exposes token-budget/fast/turbo flags but no
    # CPU-offload or sequential-load switch. Do not add unsupported flags or change weights.
    try:
        proc = subprocess.Popen(cmd, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        lines: queue.Queue[str | None] = queue.Queue()
        tail_lines: list[str] = []
        def read_output() -> None:
            try:
                assert proc.stdout is not None
                for output_line in proc.stdout:
                    lines.put(output_line.rstrip())
            finally:
                lines.put(None)
        reader = threading.Thread(target=read_output, name="budget3d-output", daemon=True)
        reader.start()
        deadline = __import__("time").monotonic() + timeout
        while proc.poll() is None:
            remaining = deadline - __import__("time").monotonic()
            if remaining <= 0:
                proc.kill()
                proc.wait()
                reader.join(timeout=2)
                raise Budget3DError(f"Budget3D exceeded {timeout}s and was stopped. Last output: {' | '.join(tail_lines[-8:])}")
            try:
                line = lines.get(timeout=min(0.4, remaining))
            except queue.Empty:
                continue
            if line:
                tail_lines.append(line)
                tail_lines = tail_lines[-80:]
                if on_log:
                    on_log(line[-1000:])
        reader.join(timeout=2)
        while True:
            try:
                line = lines.get_nowait()
            except queue.Empty:
                break
            if line:
                tail_lines.append(line)
                tail_lines = tail_lines[-80:]
                if on_log:
                    on_log(line[-1000:])
        code = proc.returncode
        lines = tail_lines
    except Budget3DError:
        raise
    except Exception as exc:
        raise Budget3DError(f"Could not start official Budget3D sampler: {exc}") from exc
    if code:
        tail = "\n".join(lines[-15:]) or "no sampler output"
        hint = " CUDA memory exhaustion or unsupported GPU precision is a likely cause." if any(k in tail.lower() for k in ("out of memory", "cuda error", "no kernel image")) else ""
        raise Budget3DError(f"Official Budget3D sampler failed (exit {code}).{hint}\n{tail}")
    if not output_ply.is_file() or output_ply.stat().st_size < 128:
        raise Budget3DError("Official sampler returned success but no valid-size Gaussian PLY was written.")
