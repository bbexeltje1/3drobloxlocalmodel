from __future__ import annotations

import io
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError
import trimesh

from backend.roblox_pipeline import export_complete_roblox_bundle
from .background_removal import run_feynobg
from .blender_bridge import BlenderBridgeError, process_with_existing_poc
from .budget3d import generate as generate_budget3d
from .gaussian_to_mesh import convert_budget3d_ply
from .preprocess import prepare_for_idol

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
GPU_JOB_LOCK = threading.Lock()

STAGES = ("background_removal", "preprocess", "gaussian_generation", "mesh_conversion", "blender", "roblox_export")


def _set_job(job_id: str, **fields: Any) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job.update(fields)
            job["updated_at"] = time.time()


def _stage(job_id: str, stage: str, status: str, message: str = "") -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return
        job["stages"][stage] = {"status": status, "message": message, "updated_at": time.time()}
        job["current_stage"] = stage if status == "running" else job.get("current_stage")
        job["updated_at"] = time.time()


def _log(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job["logs"].append(str(message)[-1500:])
            job["logs"] = job["logs"][-100:]
            job["updated_at"] = time.time()


def create_job(image_bytes: bytes, filename: str, use_background_removal: bool, budget: float,
               blender_enabled: bool, asset_name: str, preset_id: str, target_tris: int,
               target_studs: float, texture_size: int) -> str:
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Image upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Upload is not a valid supported image: {exc}") from exc
    job_id = f"single_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = Path(__file__).resolve().parents[2] / "outputs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename or "hero.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        suffix = ".png"
    original = job_dir / f"original_upload{suffix}"
    original.write_bytes(image_bytes)
    stages = {name: {"status": "pending", "message": "Waiting"} for name in STAGES}
    job = {"job_id": job_id, "status": "queued", "current_stage": None, "progress": 0,
           "message": "Queued", "stages": stages, "logs": [], "created_at": time.time(),
           "updated_at": time.time(), "files": {"original": original.name}, "result": None, "error": None,
           "options": {"background_removal": use_background_removal, "budget": budget,
                       "blender": blender_enabled, "asset_name": asset_name, "preset_id": preset_id,
                       "target_tris": target_tris, "target_studs": target_studs, "texture_size": texture_size}}
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job_id


def run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return
        data = dict(job)
    options = data["options"]
    directory = Path(__file__).resolve().parents[2] / "outputs" / job_id
    original = directory / data["files"]["original"]
    try:
        _set_job(job_id, status="running", message="Processing local image")
        # Stage 1 — explicit FeyNobg; never substitute another model.
        _stage(job_id, "background_removal", "running", "Loading local FeyNobg through the official nobg API")
        _set_job(job_id, progress=5)
        foreground = directory / "feynobg_rgba.png"
        if options["background_removal"]:
            with GPU_JOB_LOCK:
                run_feynobg(original, foreground)
        else:
            with Image.open(original) as im:
                im.convert("RGBA").save(foreground, format="PNG")
        with Image.open(foreground) as im:
            if im.format != "PNG" or im.mode != "RGBA" or im.width < 2 or im.height < 2:
                raise RuntimeError("FeyNobg output must be a valid RGBA PNG of at least 2×2 pixels.")
            im.verify()
        if options["background_removal"]:
            _stage(job_id, "background_removal", "completed", "FeyNobg RGBA saved with original size; source upload retained")
        else:
            _stage(job_id, "background_removal", "skipped", "Disabled by user; source retained and converted to RGBA without masking")
        _set_job(job_id, progress=15, files={**data["files"], "processed": foreground.name})

        # Stage 2 — only mode/compositing normalization. Idol's official ImagePreprocessor
        # remains responsible for crop/resize and the model's learned framing.
        _stage(job_id, "preprocess", "running", "Preserving full frame and aspect ratio; delegating Idol framing to official sampler")
        prepared = directory / "idol_input.png"
        image_info = prepare_for_idol(foreground, prepared)
        _stage(job_id, "preprocess", "completed", f"Prepared {image_info['width']}×{image_info['height']} full-frame image")
        _set_job(job_id, progress=22, files={**data["files"], "processed": foreground.name, "idol_input": prepared.name})

        # Stage 3 — official Budget3D scripts/sample.py in its isolated Python environment.
        _stage(job_id, "gaussian_generation", "running", f"Official Budget3D inference at {options['budget']:.4g} token budget; CUDA required")
        splat_ply = directory / "budget3d_gaussians.ply"
        with GPU_JOB_LOCK:
            generate_budget3d(prepared, splat_ply, float(options["budget"]), on_log=lambda line: _log(job_id, line))
        _stage(job_id, "gaussian_generation", "completed", "Budget3D wrote a Gaussian representation PLY (not a polygon mesh)")
        _set_job(job_id, progress=58, files={**data["files"], "processed": foreground.name,
                                            "idol_input": prepared.name, "gaussian_ply": splat_ply.name})

        # Stage 4 — converter boundary validates genuine triangle faces after external extraction.
        _stage(job_id, "mesh_conversion", "running", "Converting Gaussian PLY with explicitly configured compatible converter")
        converted_glb = directory / "converted_mesh.glb"
        raw_mesh, conversion = convert_budget3d_ply(splat_ply, converted_glb)
        _stage(job_id, "mesh_conversion", "completed", f"Validated {conversion['triangles']:,} triangle faces; watertight={conversion['watertight']}")
        _set_job(job_id, progress=72, conversion=conversion,
                 files={**data["files"], "processed": foreground.name, "idol_input": prepared.name,
                        "gaussian_ply": splat_ply.name, "converted_mesh": converted_glb.name})

        # Stage 5 — optional handoff through the already-running Spec → Blender PoC API.
        blender_note = "Blender inspection not requested; using validated mesh directly."
        _stage(job_id, "blender", "running", "Blender MCP handoff is optional")
        final_mesh_path = converted_glb
        if options["blender"]:
            try:
                glb_bytes, meta = process_with_existing_poc(converted_glb)
                if len(glb_bytes) < 128:
                    raise BlenderBridgeError("Blender returned an empty GLB.")
                final_mesh_path = directory / "blender_inspected_mesh.glb"
                final_mesh_path.write_bytes(glb_bytes)
                loaded = trimesh.load(str(final_mesh_path), force="scene")
                raw_mesh = loaded.to_geometry() if isinstance(loaded, trimesh.Scene) else loaded
                if not isinstance(raw_mesh, trimesh.Trimesh) or not len(raw_mesh.faces):
                    raise BlenderBridgeError("Blender-exported GLB contains no polygon mesh.")
                blender_note = "Inspected/exported by existing Blender MCP PoC; " + json.dumps(meta.get("blender_report", {}), separators=(",", ":"))
                _stage(job_id, "blender", "completed", blender_note)
                _set_job(job_id, files={**data["files"], "processed": foreground.name, "idol_input": prepared.name,
                                        "gaussian_ply": splat_ply.name, "converted_mesh": converted_glb.name,
                                        "blender_mesh": final_mesh_path.name})
            except Exception as exc:
                blender_note = f"Blender MCP unavailable or failed; continuing with unchanged validated mesh. {exc}"
                _stage(job_id, "blender", "skipped", blender_note)
                _log(job_id, blender_note)
                _set_job(job_id, blender_warning=str(exc))
        else:
            _stage(job_id, "blender", "skipped", blender_note)
        _set_job(job_id, progress=80)

        # Stage 6 — existing Roblox exporter; no duplicate export implementation.
        _stage(job_id, "roblox_export", "running", "Running existing RoForge cleanup, QEM, UV, maps and bundle exporter")
        with Image.open(foreground) as im:
            view = np.array(im.convert("RGBA"), dtype=np.uint8)
        bundle = export_complete_roblox_bundle(
            raw_mesh=raw_mesh, output_dir=directory, asset_name=options["asset_name"],
            preset_id=options["preset_id"], target_tris=options["target_tris"],
            texture_size=options["texture_size"], target_studs=options["target_studs"],
            views_rgba={"front": view}, engine_used="budget3d_idol",
        )
        bundle["stats"]["gaussian_conversion"] = conversion
        bundle["stats"]["source_gaussian_ply"] = splat_ply.name
        bundle["stats"]["blender_note"] = blender_note
        (directory / "roblox_validation_report.json").write_text(json.dumps(bundle["stats"], indent=2), encoding="utf-8")
        ts = int(time.time() * 1000)
        base = f"/outputs/{job_id}"
        result = {"job_id": job_id, "asset_name": bundle["asset_name"], "engine_note": blender_note,
                  "elapsed_sec": round(time.time() - data["created_at"], 2),
                  "glb_url": f"{base}/{bundle['glb_filename']}?v={ts}",
                  "obj_url": f"{base}/{bundle['obj_filename']}?v={ts}",
                  "zip_url": f"{base}/{bundle['zip_filename']}?v={ts}",
                  "maps": {key: f"{base}/SurfaceAppearance/{key}.png?v={ts}"
                           for key in ("ColorMap", "NormalMap", "MetalnessMap", "RoughnessMap")},
                  "lua_script": bundle["lua_script"], "stats": bundle["stats"]}
        _stage(job_id, "roblox_export", "completed", f"Bundle exported: {bundle['stats']['final_triangles']:,} triangles")
        _set_job(job_id, status="completed", current_stage=None, progress=100, message="Single-image workflow completed",
                 result=result, files={**data["files"], "processed": foreground.name, "idol_input": prepared.name,
                                       "gaussian_ply": splat_ply.name, "converted_mesh": converted_glb.name,
                                       **({"blender_mesh": final_mesh_path.name} if final_mesh_path != converted_glb else {}),
                                       "glb": bundle["glb_filename"], "obj": bundle["obj_filename"],
                                       "zip": bundle["zip_filename"]})
    except Exception as exc:
        current = None
        with JOBS_LOCK:
            if job_id in JOBS:
                current = JOBS[job_id].get("current_stage")
        if current in STAGES:
            _stage(job_id, current, "failed", str(exc))
        _set_job(job_id, status="failed", current_stage=current, message="Pipeline stopped; no downstream stages were claimed successful",
                 error={"stage": current, "message": str(exc)})
        _log(job_id, f"FAILED: {type(exc).__name__}: {exc}")


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        value = JOBS.get(job_id)
        return dict(value) if value is not None else None
