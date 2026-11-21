"""ComfyUI bridge for single-image Idol splats and best-effort splat-to-mesh export.

The generated Roblox mesh is an approximate surface extracted from Gaussian splats. It is
not equivalent to Idol's primary output and can be empty, blobby, or incomplete.
"""

from __future__ import annotations

import io
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import httpx
from PIL import Image, ImageOps


REQUIRED_NODE_TYPES = (
    "LoadImage",
    "InvertMask",
    "LoadBackgroundRemovalModel",
    "IdolPreprocessImage",
    "IdolCamera",
    "IdolPruneSplat",
    "CLIPVisionLoader",
    "VAELoader",
    "UNETLoader",
    "TripoSplatConditioning",
    "KSampler",
    "VAEDecodeTripoSplat",
    "RenderSplat",
    "SplatToFile3D",
    "SplatToMesh",
    "SaveGLB",
    "SaveImage",
)


def build_comfy_idol_api_prompt(
    uploaded_filename: str,
    *,
    seed: int = 42,
    mode: str = "real",
    has_alpha: bool = False,
    mesh_resolution: int = 128,
    num_gaussians: int = 262144,
    asset_prefix: str = "RoForge_Idol",
) -> Dict[str, Any]:
    """Build a ComfyUI API prompt for Idol, splat preview/turntable, PLY and mesh GLB."""
    if mode not in {"real", "synthetic"}:
        raise ValueError("Idol mode must be 'real' or 'synthetic'.")
    if not 64 <= int(mesh_resolution) <= 768:
        raise ValueError("Mesh extraction resolution must be between 64 and 768.")

    preprocess_inputs: Dict[str, Any] = {
        "image": ["1", 0],
        "mode": mode,
        "erode_radius": 1,
        "size": 1024,
    }
    graph: Dict[str, Any] = {
        "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_filename}},
        "4": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "dino_v3_vit_h.safetensors"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "6": {"class_type": "UNETLoader", "inputs": {"unet_name": "idol_fp16.safetensors", "weight_dtype": "default"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "idol_decoder_fp16.safetensors"}},
        "8": {"class_type": "TripoSplatConditioning", "inputs": {
            "clip_vision": ["4", 0], "vae": ["5", 0], "image": ["3", 0],
        }},
        "9": {"class_type": "KSampler", "inputs": {
            "model": ["6", 0], "seed": int(seed), "steps": 50, "cfg": 4.0,
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["8", 0], "negative": ["8", 1], "latent_image": ["8", 2],
            "denoise": 1.0,
        }},
        "10": {"class_type": "VAEDecodeTripoSplat", "inputs": {
            "samples": ["9", 0], "vae": ["7", 0],
            "num_gaussians": int(num_gaussians), "seed": int(seed),
        }},
        "11": {"class_type": "IdolPruneSplat", "inputs": {
            "splat": ["10", 0], "min_opacity": 0.05, "max_scale": 0.05,
        }},
        "12": {"class_type": "IdolCamera", "inputs": {"samples": ["9", 0]}},
        "13": {"class_type": "RenderSplat", "inputs": {
            "splat": ["11", 0], "width": 512, "height": 512, "frames": 1,
            "splat_scale": 1.0, "sharpen": 2.0, "headlight_shading": 0.0,
            "opacity_threshold": 0.05, "render_style": "color", "background": "#262b33",
            "camera_info": ["12", 0],
        }},
        "14": {"class_type": "SaveImage", "inputs": {
            "images": ["13", 0], "filename_prefix": f"roforge_idol/{asset_prefix}_input_view",
        }},
        "15": {"class_type": "RenderSplat", "inputs": {
            "splat": ["11", 0], "width": 320, "height": 320, "frames": 24,
            "splat_scale": 1.0, "sharpen": 2.0, "headlight_shading": 0.0,
            "opacity_threshold": 0.05, "render_style": "color", "background": "#262b33",
            "camera_info": ["12", 0],
        }},
        "16": {"class_type": "SaveImage", "inputs": {
            "images": ["15", 0], "filename_prefix": f"roforge_idol/{asset_prefix}_turntable",
        }},
        "17": {"class_type": "SplatToFile3D", "inputs": {"splat": ["11", 0], "format": "ply"}},
        "18": {"class_type": "SaveGLB", "inputs": {
            "mesh": ["17", 0], "filename_prefix": f"roforge_idol/{asset_prefix}_splat",
        }},
        # Conservative 128³ density grid to reduce VRAM pressure on 6 GB cards.
        "19": {"class_type": "SplatToMesh", "inputs": {
            "splat": ["11", 0], "resolution": int(mesh_resolution), "kernel": 5,
            "smooth": 3, "level": 0.4, "min_component": 500, "min_opacity": 0.02,
            "color_sharpen": 2.0, "solid": True, "fill": 20.0,
        }},
        "20": {"class_type": "SaveGLB", "inputs": {
            "mesh": ["19", 0], "filename_prefix": f"roforge_idol/{asset_prefix}_mesh",
        }},
    }

    if has_alpha:
        graph["2"] = {"class_type": "InvertMask", "inputs": {"mask": ["1", 1]}}
        preprocess_inputs["mask"] = ["2", 0]
    else:
        graph["2"] = {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}}
        preprocess_inputs["bg_removal_model"] = ["2", 0]
    graph["3"] = {"class_type": "IdolPreprocessImage", "inputs": preprocess_inputs}
    return graph


def _collect_saved_items(node_output: Dict[str, Any]) -> list[Dict[str, str]]:
    items: list[Dict[str, str]] = []
    for key in ("3d", "images", "videos", "result", "model_3d", "gltf", "meshes"):
        values = node_output.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and item.get("filename"):
                items.append(item)
    return items


def _download_saved_item(client: httpx.Client, base: str, item: Dict[str, str], target: Path) -> bool:
    filename = item.get("filename")
    if not filename:
        return False
    response = client.get(
        f"{base}/view",
        params={
            "filename": filename,
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        },
    )
    response.raise_for_status()
    if not response.content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    return True


def _make_turntable_gif(frames: Iterable[Image.Image], target: Path) -> Optional[Path]:
    frames = list(frames)
    if not frames:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    rgb_frames = [frame.convert("RGB") for frame in frames]
    rgb_frames[0].save(
        target,
        save_all=True,
        append_images=rgb_frames[1:],
        duration=70,
        loop=0,
        optimize=True,
    )
    return target


def run_comfy_idol_single_image(
    image_path: Path,
    *,
    output_dir: Path,
    asset_prefix: str = "RoForge_Idol",
    comfy_url: str = "http://127.0.0.1:8188",
    seed: int = 42,
    mode: str = "real",
    mesh_resolution: int = 128,
    timeout_sec: int = 1800,
) -> Dict[str, Any]:
    """Run ComfyUI Idol from one image and collect PLY, mesh (if conversion succeeds), and previews."""
    base = comfy_url.rstrip("/")
    client_id = str(uuid.uuid4())
    output_dir.mkdir(parents=True, exist_ok=True)
    input_image = ImageOps.exif_transpose(Image.open(image_path))
    alpha = input_image.convert("RGBA").getchannel("A")
    has_alpha = alpha.getextrema() != (255, 255)
    png_buffer = io.BytesIO()
    input_image.convert("RGBA").save(png_buffer, format="PNG")
    png_bytes = png_buffer.getvalue()
    upload_name = f"roforge_idol_{client_id[:10]}.png"

    try:
        with httpx.Client(timeout=60.0) as client:
            stats = client.get(f"{base}/system_stats")
            stats.raise_for_status()
            info_resp = client.get(f"{base}/object_info")
            info_resp.raise_for_status()
            available = info_resp.json()
            missing = [name for name in REQUIRED_NODE_TYPES if name not in available]
            if missing:
                raise RuntimeError(
                    "ComfyUI is missing Idol workflow nodes: " + ", ".join(missing) + ". "
                    "Run scripts\\setup_comfyui_idol_windows.bat, restart ComfyUI, and retry."
                )
            up = client.post(
                f"{base}/upload/image",
                files={"image": (upload_name, png_bytes, "image/png")},
                data={"overwrite": "true"},
            )
            up.raise_for_status()
            uploaded_filename = up.json().get("name", upload_name)
            prompt = build_comfy_idol_api_prompt(
                uploaded_filename,
                seed=seed,
                mode=mode,
                has_alpha=has_alpha,
                mesh_resolution=mesh_resolution,
                asset_prefix=asset_prefix,
            )
            queued = client.post(f"{base}/prompt", json={"prompt": prompt, "client_id": client_id})
            if queued.is_error:
                try:
                    error_data = queued.json()
                except ValueError:
                    error_data = queued.text
                raise RuntimeError(f"ComfyUI rejected the Idol workflow: {error_data}")
            prompt_id = queued.json()["prompt_id"]

        deadline = time.time() + timeout_sec
        final_outputs: Dict[str, Any] = {}
        execution_error = ""
        with httpx.Client(timeout=45.0) as client:
            while time.time() < deadline:
                history_resp = client.get(f"{base}/history/{prompt_id}")
                if history_resp.status_code == 200:
                    history = history_resp.json()
                    entry = history.get(prompt_id)
                    if entry:
                        final_outputs = entry.get("outputs", {}) or {}
                        status = entry.get("status", {})
                        if status.get("completed"):
                            break
                        messages = status.get("messages", [])
                        for message in messages:
                            if isinstance(message, (list, tuple)) and message and message[0] == "execution_error":
                                detail = message[1] if len(message) > 1 else {}
                                execution_error = (
                                    str(detail.get("exception_message", detail))
                                    if isinstance(detail, dict)
                                    else str(detail)
                                )
                                break
                        if execution_error:
                            break
                time.sleep(2.0)
            else:
                raise TimeoutError(f"ComfyUI Idol exceeded its {timeout_sec // 60}-minute timeout.")

            result: Dict[str, Any] = {"ply_path": None, "mesh_glb_path": None, "preview_path": None, "turntable_path": None}
            output_map = {str(key): value for key, value in final_outputs.items()}
            splat_items = _collect_saved_items(output_map.get("18", {}))
            mesh_items = _collect_saved_items(output_map.get("20", {}))
            preview_items = _collect_saved_items(output_map.get("14", {}))
            turntable_items = _collect_saved_items(output_map.get("16", {}))

            for item in splat_items:
                if Path(item["filename"]).suffix.lower() == ".ply":
                    target = output_dir / f"{asset_prefix}_gaussian.ply"
                    try:
                        if _download_saved_item(client, base, item, target):
                            result["ply_path"] = target
                            break
                    except httpx.HTTPError:
                        continue
            for item in mesh_items:
                if Path(item["filename"]).suffix.lower() in {".glb", ".gltf"}:
                    target = output_dir / f"{asset_prefix}_splat_mesh.glb"
                    try:
                        if _download_saved_item(client, base, item, target):
                            result["mesh_glb_path"] = target
                            break
                    except httpx.HTTPError:
                        continue
            for item in preview_items:
                if Path(item["filename"]).suffix.lower() == ".png":
                    target = output_dir / f"{asset_prefix}_idol_preview.png"
                    try:
                        if _download_saved_item(client, base, item, target):
                            result["preview_path"] = target
                            break
                    except httpx.HTTPError:
                        continue

            frame_images: list[Image.Image] = []
            for item in sorted(turntable_items, key=lambda x: x.get("filename", "")):
                if Path(item["filename"]).suffix.lower() != ".png":
                    continue
                try:
                    response = client.get(
                        f"{base}/view",
                        params={
                            "filename": item["filename"],
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        },
                    )
                    response.raise_for_status()
                    frame_images.append(Image.open(io.BytesIO(response.content)).convert("RGB"))
                except Exception:
                    continue
            result["turntable_path"] = _make_turntable_gif(frame_images, output_dir / f"{asset_prefix}_turntable.gif")
            result["execution_error"] = execution_error

            if not result["ply_path"]:
                detail = execution_error or "ComfyUI completed, but no Gaussian-splat PLY was saved."
                raise RuntimeError(f"ComfyUI Idol did not produce its primary PLY output: {detail}")
            if not result["mesh_glb_path"]:
                result["mesh_error"] = execution_error or "The splat-to-mesh node did not create a GLB."
            return result
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach local ComfyUI at {base}. Start ComfyUI with scripts\\start_comfyui_6gb.bat and verify its URL."
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Timed out while communicating with ComfyUI at {base}.") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"ComfyUI request failed at {base}: {exc}") from exc
