"""Local-only RoForge spec-to-Blender MCP proof of concept."""
from __future__ import annotations

import base64
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from blender_script import build_script
from mcp_client import BlenderMCPClient, BlenderMCPError
from spec import require_approval, starter_spec, validate_spec

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
OUTPUTS = Path(os.getenv("POC_OUTPUT_DIR", str(ROOT / "outputs"))).expanduser().resolve()
VLM_URL = os.getenv("POC_VLM_URL", "").strip()
VLM_PROVIDER = os.getenv("POC_VLM_PROVIDER", "openai").strip().lower()
VLM_MODEL = os.getenv("POC_VLM_MODEL", "qwen2.5vl:3b").strip()
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.blender_mcp = BlenderMCPClient()
    yield
    await app.state.blender_mcp.close()


app = FastAPI(title="RoForge Spec → Blender PoC", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def local_origin_guard(request, call_next):
    # App is intended to bind to loopback. Reject cross-site state-changing requests too.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            try:
                origin_host = urlparse(origin).hostname
            except ValueError:
                origin_host = None
            if origin_host not in {"127.0.0.1", "localhost"}:
                return JSONResponse({"detail": "Cross-origin requests are not allowed by the local PoC."}, status_code=403)
        if origin and origin.rstrip("/") != f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse({"detail": "Cross-origin requests are not allowed by the local PoC."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not allowed by the local PoC."}, status_code=403)
    host_header = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
    if host_header and host_header not in {"127.0.0.1", "localhost", "::1"}:
        return JSONResponse({"detail": "This PoC only accepts loopback hostnames."}, status_code=403)
    return await call_next(request)


def _ensure_local_vlm_url() -> None:
    parsed = urlparse(VLM_URL)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=400, detail="POC_VLM_URL must point to a local loopback endpoint; reference images are never sent off this PC.")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": "local-only",
        "vlm_configured": bool(VLM_URL),
        "vlm_model": VLM_MODEL if VLM_URL else None,
        "vlm_provider": VLM_PROVIDER if VLM_URL else None,
        "blender_connection": "not tested yet",
        "output_directory": str(OUTPUTS),
    }


@app.get("/api/starter-spec")
def get_starter_spec():
    return starter_spec()


async def _read_upload(upload: UploadFile) -> tuple[str, str]:
    content_type = upload.content_type or ""
    if content_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'Uploaded file'} must be PNG, JPEG, WebP, or GIF.")
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Each reference image must be 10 MB or smaller.")
    mime = content_type if content_type in {"image/png", "image/jpeg", "image/webp", "image/gif"} else "image/png"
    return mime, base64.b64encode(data).decode("ascii")


def _json_from_model(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    if not isinstance(content, str):
        raise ValueError("The local vision model did not return text JSON.")
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S | re.I)
    if fence:
        text = fence.group(1)
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char == "{":
            try:
                value, _ = decoder.raw_decode(text[start:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    raise ValueError("Could not find a JSON object in the local model response. Try again or edit the starter spec manually.")


@app.post("/api/draft-spec")
async def draft_spec(
    prompt: str = Form(...),
    references: list[UploadFile] = File(default=[]),
):
    if not VLM_URL:
        raise HTTPException(
            status_code=503,
            detail=("No local vision-language model endpoint is configured. The included starter spec is ready to edit. "
                    "To enable drafting from text/images, set POC_VLM_URL to your local OpenAI-compatible vision endpoint and restart the app."),
        )
    _ensure_local_vlm_url()
    if len(references) > 4:
        raise HTTPException(status_code=400, detail="Upload up to four reference images.")

    images: list[tuple[str, str]] = []
    for upload in references:
        mime, encoded = await _read_upload(upload)
        images.append((mime, encoded))

    guide = (
        "You are a careful asset-spec assistant. Use the user text and reference images to return ONE JSON object only. "
        "Use this structure: {asset_name:string, unit_mode:string, overall:{length:number,height:number,width:number,source_note:string}, "
        "palette:{semantic_name:'#RRGGBB'}, parts:[{id,label,count,color,kind,exact,provisional?}], "
        "motions:[{part_id,type,angle_degrees,axis,timing,pivot,provisional}], unknowns:[string], "
        "approval:{reviewed_by_user:false}}. Never invent exact dimensions, counts, hex codes, pivots, or motion details: "
        "copy supplied values; otherwise mark estimates provisional and add a clear item to unknowns. Dimensions inferred from a picture "
        "are not measurements. Keep color references by palette key. Exact counts explicitly stated by the user may have exact:true. "
        "Keep part ids lowercase snake_case. Do not include markdown or executable code."
    )
    user_text = guide + "\n\nUser design request:\n" + prompt
    if VLM_PROVIDER == "ollama":
        payload = {"model": VLM_MODEL, "stream": False, "format": "json",
                   "messages": [{"role": "user", "content": user_text, "images": [encoded for _mime, encoded in images]}]}
    elif VLM_PROVIDER == "openai":
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        content.extend({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}} for mime, encoded in images)
        payload = {"model": VLM_MODEL, "messages": [{"role": "user", "content": content}], "temperature": 0.1}
    else:
        raise HTTPException(status_code=400, detail="POC_VLM_PROVIDER must be 'ollama' or 'openai'.")
    try:
        async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
            response = await client.post(VLM_URL, json=payload)
            response.raise_for_status()
        data = response.json()
        answer = data["message"]["content"] if VLM_PROVIDER == "ollama" else data["choices"][0]["message"]["content"]
        spec = _json_from_model(answer)
        spec, unknowns = validate_spec(spec)
        spec.setdefault("approval", {})["reviewed_by_user"] = False
        return {"spec": spec, "unknowns": unknowns, "notice": "Draft only. Review counts, colors, units, and unknowns before building."}
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Local VLM draft failed: {exc}") from exc


@app.get("/api/blender/status")
async def blender_status():
    try:
        return await app.state.blender_mcp.status()
    except BlenderMCPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/build")
async def build_asset(payload: dict[str, Any]):
    try:
        spec, unknowns = validate_spec(payload.get("spec"))
        supported_parts = {"primary_feathers", "turkey_receiver", "corn_cobs", "kernel_rows_per_cob", "pie_coil_rings", "cranberry_can_ribs", "wishbone_muzzle", "trigger", "magazine", "wattle"}
        part_ids = {part["id"] for part in spec["parts"]}
        unsupported = sorted(part_ids - supported_parts)
        missing = sorted(supported_parts - part_ids)
        if unsupported or missing:
            details = []
            if unsupported:
                details.append("unsupported: " + ", ".join(unsupported))
            if missing:
                details.append("missing required draft parts: " + ", ".join(missing))
            raise ValueError("This Gobble Rail PoC builder supports its listed starter part IDs only (" + "; ".join(details) + ").")
        require_approval(spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = payload.get("prompt", "Build the approved RoForge structured asset spec in Blender.")
    if not isinstance(prompt, str):
        prompt = "Build the approved RoForge structured asset spec in Blender."
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", spec["asset_name"]).strip("_-") or "Gobble_Rail_POC"
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    glb_path = OUTPUTS / f"{slug}.glb"
    spec_path = OUTPUTS / f"{slug}.json"
    script = build_script(spec, glb_path)
    try:
        # Save the approved source spec locally; the Blender scene only receives generated Python.
        spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
        result = await app.state.blender_mcp.execute(script, prompt)
    except (OSError, BlenderMCPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "asset_name": spec["asset_name"],
        "output_filename": glb_path.name,
        "result": result,
        "glb_path": str(glb_path),
        "spec_path": str(spec_path),
        "unknowns": unknowns,
        "note": "GLB exported from a dedicated PoC collection. The current .blend file is not saved or overwritten.",
    }


@app.get("/api/output/{filename}")
def get_output(filename: str):
    if (Path(filename).name != filename or "/" in filename or "\\" in filename
            or not filename.lower().endswith((".glb", ".json"))):
        raise HTTPException(status_code=400, detail="Invalid output filename.")
    path = (OUTPUTS / filename).resolve()
    if path.parent != OUTPUTS or not path.is_file():
        raise HTTPException(status_code=404, detail="Output not found.")
    return FileResponse(path)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="ui")
