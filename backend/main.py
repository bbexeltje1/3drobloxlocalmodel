"""FastAPI Server for RoForge 3D — Local Roblox Multi-View 3D Asset Creator."""

from __future__ import annotations

import io
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional, Dict

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import psutil
import trimesh

from .presets import ROBLOX_PRESETS, HF_MODELS_6GB_CATALOG, ROBLOX_HARD_MESHPART_TRI_CAP
from .roblox_pipeline import (
    normalize_view_canvas,
    extract_pbr_maps_from_glb_scene,
    export_complete_roblox_bundle,
)
from .sample_generator import ensure_sample_sheets_generated, SAMPLE_CATALOG
from .engines.visual_hull import reconstruct_multiview_visual_hull
from .engines.comfy_pixal3d import check_comfyui_status, run_comfy_pixal3d_multiview
from .engines.hunyuan_mv import is_hunyuan_available, run_hunyuan3d_2mv_lowvram
from .single_image.background_removal import local_status as feynobg_local_status
from .single_image.budget3d import status as budget3d_local_status
from .single_image.gaussian_to_mesh import conversion_status as gaussian_conversion_status
from .single_image.blender_bridge import BlenderBridgeError, existing_poc_status
from .single_image.pipeline import create_job as create_single_image_job, get_job as get_single_image_job, run_job as run_single_image_job

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SAMPLES_DIR = ROOT_DIR / "samples"
OUTPUTS_DIR = ROOT_DIR / "outputs"
WORKFLOWS_DIR = ROOT_DIR / "workflows"

SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="RoForge 3D — Local Multi-View Roblox Asset Creator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _detect_local_hardware(comfy_url: str = "http://127.0.0.1:8188") -> Dict:
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    cuda_available = False
    gpu_name = None
    vram_gb = None
    try:
        import torch
        if torch.cuda.is_available():
            cuda_available = True
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
    except Exception:
        pass

    comfy_status = check_comfyui_status(comfy_url=comfy_url)
    if comfy_status["online"] and not gpu_name:
        gpu_name = comfy_status["device_name"]
        vram_gb = comfy_status["vram_total_gb"]

    hunyuan_ready = is_hunyuan_available()
    return {
        "system_ram_gb": ram_gb,
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "comfy_pixal3d": comfy_status,
        "hunyuan_2mv_ready": hunyuan_ready,
        "visual_hull_cpu_ready": True,
        "target_spec_summary": "Tuned for 6 GB VRAM + 32 GB System RAM (--lowvram --disable-pinned-memory)",
    }


def _ensure_initial_demo() -> Dict:
    """Ensure a ready-to-inspect 3D asset exists on startup so the viewport loads immediately."""
    ensure_sample_sheets_generated(SAMPLES_DIR)
    demo_dir = OUTPUTS_DIR / "starter_dragon_helm"
    glb_file = demo_dir / "Crimson_Dragon_Helm_roblox.glb"
    report_file = demo_dir / "roblox_validation_report.json"

    if not glb_file.exists() or not report_file.exists():
        views = {}
        for v in ("front", "left", "back", "right"):
            img = Image.open(SAMPLES_DIR / "dragon_helm" / f"{v}.png")
            views[v] = normalize_view_canvas(img, size=512)
        raw_mesh = reconstruct_multiview_visual_hull(views, grid_res=104, roundness=0.38)
        export_complete_roblox_bundle(
            raw_mesh=raw_mesh,
            output_dir=demo_dir,
            asset_name="Crimson_Dragon_Helm",
            preset_id="ugc_hat",
            views_rgba=views,
            metallic_bias=0.62,
            roughness_bias=0.35,
            engine_used="visual_hull",
        )

    import json
    stats = json.loads(report_file.read_text(encoding="utf-8"))
    lua_script = (demo_dir / "setup_surface_appearance.lua").read_text(encoding="utf-8")
    return _format_job_response("starter_dragon_helm", "Crimson_Dragon_Helm", stats, lua_script, 0.0)


def _format_job_response(
    job_id: str,
    slug: str,
    stats: Dict,
    lua_script: str,
    elapsed_sec: float,
    engine_note: str = "",
) -> Dict:
    ts = int(time.time() * 1000)
    base = f"/outputs/{job_id}"
    return {
        "job_id": job_id,
        "asset_name": slug,
        "elapsed_sec": round(elapsed_sec, 2),
        "engine_note": engine_note,
        "glb_url": f"{base}/{slug}_roblox.glb?v={ts}",
        "obj_url": f"{base}/{slug}_roblox.obj?v={ts}",
        "zip_url": f"{base}/{slug}_RobloxStudio_Bundle.zip?v={ts}",
        "maps": {
            "ColorMap": f"{base}/SurfaceAppearance/ColorMap.png?v={ts}",
            "NormalMap": f"{base}/SurfaceAppearance/NormalMap.png?v={ts}",
            "MetalnessMap": f"{base}/SurfaceAppearance/MetalnessMap.png?v={ts}",
            "RoughnessMap": f"{base}/SurfaceAppearance/RoughnessMap.png?v={ts}",
        },
        "lua_script": lua_script,
        "stats": stats,
    }


@app.on_event("startup")
def on_startup() -> None:
    _ensure_initial_demo()


@app.get("/api/status")
def api_status(comfy_url: str = "http://127.0.0.1:8188"):
    return {
        "hardware": _detect_local_hardware(comfy_url=comfy_url),
        "presets": ROBLOX_PRESETS,
        "hf_models": HF_MODELS_6GB_CATALOG,
        "meshpart_hard_cap": ROBLOX_HARD_MESHPART_TRI_CAP,
        "starter_asset": _ensure_initial_demo(),
    }


@app.get("/api/samples")
def api_samples():
    return {"samples": ensure_sample_sheets_generated(SAMPLES_DIR)}


@app.get("/api/workflow-json")
def api_workflow_json():
    wf_path = WORKFLOWS_DIR / "roblox_pixal3d_multiview_6gb.json"
    if not wf_path.exists():
        raise HTTPException(status_code=404, detail="Workflow JSON not found.")
    return FileResponse(
        str(wf_path),
        media_type="application/json",
        filename="roblox_pixal3d_multiview_6gb.json",
    )


@app.post("/api/generate")
async def api_generate(
    engine: str = Form("auto"),
    comfy_url: str = Form("http://127.0.0.1:8188"),
    sample_id: Optional[str] = Form(None),
    asset_name: str = Form("Roblox_Asset"),
    preset_id: str = Form("weapon_tool"),
    target_tris: int = Form(7500),
    texture_size: int = Form(1024),
    target_studs: float = Form(4.0),
    roundness: float = Form(0.38),
    grid_res: int = Form(104),
    metallic_bias: float = Form(0.35),
    roughness_bias: float = Form(0.50),
    seed: int = Form(42),
    front: Optional[UploadFile] = File(None),
    left: Optional[UploadFile] = File(None),
    back: Optional[UploadFile] = File(None),
    right: Optional[UploadFile] = File(None),
):
    t0 = time.time()
    job_id = f"job_{int(t0)}_{uuid.uuid4().hex[:6]}"
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir = job_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    pil_views: Dict[str, Image.Image] = {}
    uploaded_map = {"front": front, "left": left, "back": back, "right": right}
    for vname, up in uploaded_map.items():
        if up is not None and up.filename:
            raw_bytes = await up.read()
            if raw_bytes:
                pil_views[vname] = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")

    if not pil_views and sample_id:
        ensure_sample_sheets_generated(SAMPLES_DIR)
        sdir = SAMPLES_DIR / sample_id
        if not sdir.exists():
            raise HTTPException(status_code=400, detail=f"Unknown sample_id: {sample_id}")
        for vname in ("front", "left", "back", "right"):
            vp = sdir / f"{vname}.png"
            if vp.exists():
                pil_views[vname] = Image.open(vp).convert("RGBA")

    if not pil_views:
        raise HTTPException(
            status_code=400,
            detail="Upload at least 1–4 turnaround views (Front / Left / Back / Right) or pick a Sample Sheet.",
        )

    # Normalize all supplied views to consistent height-aligned 512x512 RGBA canvases
    norm_views = {}
    saved_view_paths: Dict[str, Path] = {}
    for vname, pimg in pil_views.items():
        arr = normalize_view_canvas(pimg, size=512)
        norm_views[vname] = arr
        vp = inputs_dir / f"{vname}.png"
        Image.fromarray(arr, mode="RGBA").save(vp, format="PNG")
        saved_view_paths[vname] = vp

    # Resolve requested engine against available local backends
    chosen_engine = engine
    engine_note = ""
    if chosen_engine == "auto":
        if check_comfyui_status(comfy_url=comfy_url)["online"]:
            chosen_engine = "comfy_pixal3d"
            engine_note = "Connected to local ComfyUI Pixal3D Multi-View (6 GB VRAM profile)."
        elif is_hunyuan_available():
            chosen_engine = "hunyuan_mv"
            engine_note = "Executed local Hunyuan3D-2mv-Turbo (FP16 6 GB VRAM profile)."
        else:
            chosen_engine = "visual_hull"
            engine_note = (
                "Generated via built-in Local Multi-View Visual-Hull + PBR Baker (CPU, 0 GB VRAM). "
                "Start ComfyUI with start_comfyui_6gb.bat to switch to Pixal3D Multi-View AI!"
            )

    existing_maps = None
    if chosen_engine == "comfy_pixal3d":
        status = check_comfyui_status(comfy_url=comfy_url)
        if not status["online"]:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Local ComfyUI not reachable at {comfy_url}. "
                    "Launch ComfyUI using scripts/start_comfyui_6gb.bat (.sh) or switch Engine to Auto / Visual-Hull."
                ),
            )
        raw_glb = job_dir / "comfy_raw.glb"
        run_comfy_pixal3d_multiview(
            view_images={k: Image.fromarray(v, mode="RGBA") for k, v in norm_views.items()},
            out_glb_path=raw_glb,
            comfy_url=comfy_url,
            target_tris=target_tris,
            texture_size=texture_size,
            seed=seed,
        )
        loaded = trimesh.load(str(raw_glb))
        existing_maps = extract_pbr_maps_from_glb_scene(loaded, texture_size=texture_size)
        raw_mesh = (
            trimesh.util.concatenate(list(loaded.geometry.values()))
            if isinstance(loaded, trimesh.Scene)
            else loaded
        )
        engine_note = f"Generated via ComfyUI Pixal3D Multi-View ({status.get('device_name')})."

    elif chosen_engine == "hunyuan_mv":
        if not is_hunyuan_available():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Local CUDA + hy3dgen not installed in current Python env. "
                    "Run scripts/download_models_6gb.py --profile hunyuan or select Auto / ComfyUI Pixal3D."
                ),
            )
        raw_mesh = run_hunyuan3d_2mv_lowvram(
            view_paths=saved_view_paths,
            seed=seed,
            octree_resolution=256,
            steps=8,
        )
        engine_note = "Generated via Tencent Hunyuan3D-2mv-Turbo (6 GB VRAM) + Camera-Projected PBR."

    else:
        raw_mesh = reconstruct_multiview_visual_hull(
            views_rgba=norm_views,
            grid_res=grid_res,
            roundness=roundness,
        )
        if not engine_note:
            engine_note = f"Reconstructed from {len(norm_views)} orthographic view(s) via Local Visual-Hull + PBR Baker."

    bundle = export_complete_roblox_bundle(
        raw_mesh=raw_mesh,
        output_dir=job_dir,
        asset_name=asset_name,
        preset_id=preset_id,
        target_tris=target_tris,
        texture_size=texture_size,
        target_studs=target_studs,
        views_rgba=norm_views,
        existing_maps=existing_maps,
        metallic_bias=metallic_bias,
        roughness_bias=roughness_bias,
        engine_used=chosen_engine,
    )

    elapsed = time.time() - t0
    return JSONResponse(
        _format_job_response(
            job_id=job_id,
            slug=bundle["asset_name"],
            stats=bundle["stats"],
            lua_script=bundle["lua_script"],
            elapsed_sec=elapsed,
            engine_note=engine_note,
        )
    )


@app.post("/api/optimize-mesh")
async def api_optimize_mesh(
    mesh_file: UploadFile = File(...),
    asset_name: str = Form("Optimized_Roblox_Asset"),
    preset_id: str = Form("weapon_tool"),
    target_tris: int = Form(7500),
    texture_size: int = Form(1024),
    target_studs: float = Form(4.0),
    metallic_bias: float = Form(0.30),
    roughness_bias: float = Form(0.55),
):
    """Import ANY raw .glb / .obj / .ply mesh (e.g. 500k-tri AI output), decimate to Roblox cap,
    and split embedded glTF metallicRoughness textures into 4 Roblox SurfaceAppearance PNG maps.
    """
    t0 = time.time()
    suffix = Path(mesh_file.filename or "model.glb").suffix.lower()
    if suffix not in (".glb", ".gltf", ".obj", ".ply", ".stl"):
        raise HTTPException(status_code=400, detail="Supported 3D formats: .glb, .obj, .ply, .stl")

    job_id = f"opt_{int(t0)}_{uuid.uuid4().hex[:6]}"
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    src_path = job_dir / f"uploaded_source{suffix}"
    src_path.write_bytes(await mesh_file.read())

    loaded = trimesh.load(str(src_path))
    existing_maps = extract_pbr_maps_from_glb_scene(loaded, texture_size=texture_size)
    raw_mesh = (
        trimesh.util.concatenate(list(loaded.geometry.values()))
        if isinstance(loaded, trimesh.Scene)
        else loaded
    )

    bundle = export_complete_roblox_bundle(
        raw_mesh=raw_mesh,
        output_dir=job_dir,
        asset_name=asset_name,
        preset_id=preset_id,
        target_tris=target_tris,
        texture_size=texture_size,
        target_studs=target_studs,
        existing_maps=existing_maps,
        metallic_bias=metallic_bias,
        roughness_bias=roughness_bias,
        engine_used="mesh_optimizer",
    )

    elapsed = time.time() - t0
    note = (
        "Decimated & unpacked embedded glTF PBR into 4 Roblox SurfaceAppearance PNGs."
        if existing_maps
        else "Decimated & generated UV-unwrapped Roblox SurfaceAppearance PBR maps."
    )
    return JSONResponse(
        _format_job_response(
            job_id=job_id,
            slug=bundle["asset_name"],
            stats=bundle["stats"],
            lua_script=bundle["lua_script"],
            elapsed_sec=elapsed,
            engine_note=note,
        )
    )


@app.get("/api/single-image/config")
def single_image_config():
    """Report local paths/runtime availability without downloading or loading model weights."""
    return {
        "feynobg": feynobg_local_status(),
        "budget3d": budget3d_local_status(),
        "gaussian_to_mesh": gaussian_conversion_status(),
        "blender_poc_url": os.getenv("BLENDER_POC_URL", "http://127.0.0.1:8765"),
        "notes": [
            "Budget3D's official sampler uses Idol ImagePreprocessor internally.",
            "Budget3D Gaussian PLY is never passed directly to the triangle-mesh optimizer.",
            "No model weights or external code are downloaded by this application.",
        ],
    }


@app.get("/api/single-image/blender-status")
def single_image_blender_status():
    try:
        # This queries the already-running PoC, which owns the only MCP client session.
        return existing_poc_status()
    except BlenderBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/single-image")
async def single_image_generate(
    background_tasks: BackgroundTasks,
    hero_image: UploadFile = File(...),
    remove_background: bool = Form(True),
    token_budget: float = Form(0.0625),
    blender_inspection: bool = Form(False),
    asset_name: str = Form("Single_Image_Asset"),
    preset_id: str = Form("weapon_tool"),
    target_tris: int = Form(7500),
    target_studs: float = Form(4.2),
    texture_size: int = Form(1024),
):
    if preset_id not in ROBLOX_PRESETS:
        raise HTTPException(status_code=400, detail="Unknown Roblox preset.")
    if not 0.0625 <= token_budget <= 1.0:
        raise HTTPException(status_code=400, detail="Budget3D token budget must be from 0.0625 to 1.0.")
    if target_tris < 200 or target_tris > ROBLOX_HARD_MESHPART_TRI_CAP - 100:
        raise HTTPException(status_code=400, detail="Triangle target is outside the supported MeshPart range.")
    content = await hero_image.read(25 * 1024 * 1024 + 1)
    try:
        job_id = create_single_image_job(
            image_bytes=content, filename=hero_image.filename or "hero.png",
            use_background_removal=remove_background, budget=token_budget,
            blender_enabled=blender_inspection, asset_name=asset_name or "Single_Image_Asset",
            preset_id=preset_id, target_tris=target_tris, target_studs=target_studs,
            texture_size=texture_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_single_image_job, job_id)
    return {"job_id": job_id, "status_url": f"/api/single-image/{job_id}", "message": "Job accepted"}


@app.get("/api/single-image/{job_id}")
def single_image_job_status(job_id: str):
    job = get_single_image_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Single-image job not found.")
    return job


app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
