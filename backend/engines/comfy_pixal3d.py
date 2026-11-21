"""ComfyUI Bridge for Pixal3D Multi-View (Comfy-Org/Pixal3D INT8 & Aero-Ex/Pixal3D-GGUF).
Compiles the official ComfyUI 3D Pixal3D Multi-View graph tuned specifically for:
- 6 GB VRAM + 32 GB System RAM (512³ grid, 384 remesh, 1024x1024 PBR bake, INT8 ConvRot)
- Roblox Studio MeshPart / UGC triangle budgets (DecimateMesh set directly to target_tris)
"""

from __future__ import annotations

import io
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from PIL import Image


def check_comfyui_status(comfy_url: str = "http://127.0.0.1:8188", timeout: float = 1.5) -> Dict[str, Any]:
    """Probe local ComfyUI server and inspect available GPU/VRAM stats."""
    url = comfy_url.rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{url}/system_stats")
            if r.status_code == 200:
                data = r.json()
                devices = data.get("devices", [])
                gpu_info = devices[0] if devices else {}
                vram_total_gb = round(gpu_info.get("vram_total", 0) / (1024 ** 3), 2)
                return {
                    "online": True,
                    "url": url,
                    "device_name": gpu_info.get("name", "Detected GPU"),
                    "vram_total_gb": vram_total_gb,
                }
    except Exception:
        pass
    return {"online": False, "url": url, "device_name": None, "vram_total_gb": None}


def build_pixal3d_mv_api_prompt(
    uploaded_filenames: Dict[str, str],
    target_tris: int = 7500,
    texture_size: int = 1024,
    voxel_res: int = 512,
    seed: int = 42,
    fov: float = 20.0,
    unet_name: str = "pixal3d_multiview_int8_convrot.safetensors",
) -> Dict[str, Any]:
    """Build ComfyUI /prompt API payload for native Pixal3DMultiViewConditioning (6 GB VRAM tuned)."""
    front_fn = uploaded_filenames["front"]
    left_fn = uploaded_filenames.get("left", front_fn)
    back_fn = uploaded_filenames.get("back", front_fn)
    right_fn = uploaded_filenames.get("right", left_fn)

    # Current ComfyUI requires Trellis2UpsampleStage.target_resolution >= 1024.
    # Keep the minimum supported value for the 6 GB VRAM profile.
    vox_res = 1024
    remesh_res = 384
    crop_res = 512

    return {
        "15": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": "dino_v3_L_naf_fp32.safetensors"},
        },
        "117": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "trellis_2_shape_vae_bf16.safetensors"},
        },
        "118": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "trellis_2_texture_vae_bf16.safetensors"},
        },
        "193": {
            "class_type": "LoadBackgroundRemovalModel",
            "inputs": {"bg_removal_name": "birefnet.safetensors"},
        },
        "319": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "401": {"class_type": "LoadImage", "inputs": {"image": front_fn}},
        "402": {"class_type": "LoadImage", "inputs": {"image": left_fn}},
        "403": {"class_type": "LoadImage", "inputs": {"image": back_fn}},
        "404": {"class_type": "LoadImage", "inputs": {"image": right_fn}},
        "192": {
            "class_type": "RemoveBackground",
            "inputs": {"bg_removal_model": ["193", 0], "image": ["401", 0]},
        },
        "348": {
            "class_type": "RemoveBackground",
            "inputs": {"bg_removal_model": ["193", 0], "image": ["402", 0]},
        },
        "351": {
            "class_type": "RemoveBackground",
            "inputs": {"bg_removal_model": ["193", 0], "image": ["403", 0]},
        },
        "353": {
            "class_type": "RemoveBackground",
            "inputs": {"bg_removal_model": ["193", 0], "image": ["404", 0]},
        },
        "312": {
            "class_type": "ImageCropToMask",
            "inputs": {
                "images": ["401", 0],
                "masks": ["192", 0],
                "width": crop_res,
                "height": crop_res,
                "pad_factor": 1.1,
                "grow_mask": 0,
                "background": "#000000",
            },
        },
        "349": {
            "class_type": "ImageCropToMask",
            "inputs": {
                "images": ["402", 0],
                "masks": ["348", 0],
                "width": crop_res,
                "height": crop_res,
                "pad_factor": 1.1,
                "grow_mask": 0,
                "background": "#000000",
            },
        },
        "350": {
            "class_type": "ImageCropToMask",
            "inputs": {
                "images": ["403", 0],
                "masks": ["351", 0],
                "width": crop_res,
                "height": crop_res,
                "pad_factor": 1.1,
                "grow_mask": 0,
                "background": "#000000",
            },
        },
        "352": {
            "class_type": "ImageCropToMask",
            "inputs": {
                "images": ["404", 0],
                "masks": ["353", 0],
                "width": crop_res,
                "height": crop_res,
                "pad_factor": 1.1,
                "grow_mask": 0,
                "background": "#000000",
            },
        },
        "324": {
            "class_type": "Pixal3DMultiViewConditioning",
            "inputs": {
                "clip_vision_model": ["15", 0],
                "front": ["312", 0],
                "left": ["349", 0],
                "back": ["350", 0],
                "right": ["352", 0],
                "fov": float(fov),
            },
        },
        "87": {"class_type": "EmptyTrellis2LatentStructure", "inputs": {"batch_size": 1}},
        "199": {
            "class_type": "CFGOverride",
            "inputs": {"model": ["319", 0], "cfg": 1.0, "start_percent": 0.667, "end_percent": 1.0},
        },
        "125": {"class_type": "RescaleCFG", "inputs": {"model": ["199", 0], "multiplier": 0.7}},
        "108": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["125", 0], "shift": 5.0}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["108", 0],
                "positive": ["324", 0],
                "negative": ["324", 1],
                "latent_image": ["87", 0],
                "seed": int(seed),
                "steps": 12,
                "cfg": 7.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "119": {
            "class_type": "VaeDecodeStructureTrellis2",
            "inputs": {"samples": ["3", 0], "vae": ["117", 0], "resolution": "32"},
        },
        "91": {
            "class_type": "Trellis2ShapeStage",
            "inputs": {
                "positive": ["324", 0],
                "negative": ["324", 1],
                "voxel": ["119", 0],
            },
        },
        "279": {
            "class_type": "CFGOverride",
            "inputs": {"model": ["319", 0], "cfg": 1.0, "start_percent": 0.769, "end_percent": 1.0},
        },
        "126": {"class_type": "RescaleCFG", "inputs": {"model": ["279", 0], "multiplier": 0.5}},
        "18": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["126", 0],
                "positive": ["91", 0],
                "negative": ["91", 1],
                "latent_image": ["91", 2],
                "seed": int(seed),
                "steps": 16,
                "cfg": 7.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "94": {
            "class_type": "Trellis2UpsampleStage",
            "inputs": {
                "positive": ["91", 0],
                "negative": ["91", 1],
                "shape_latent": ["18", 0],
                "vae": ["117", 0],
                "target_resolution": vox_res,
            },
        },
        "23": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["126", 0],
                "positive": ["94", 0],
                "negative": ["94", 1],
                "latent_image": ["94", 2],
                "seed": int(seed),
                "steps": 12,
                "cfg": 7.5,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "92": {
            "class_type": "VaeDecodeShapeTrellis",
            "inputs": {"samples": ["23", 0], "vae": ["117", 0]},
        },
        "98": {
            "class_type": "Trellis2TextureStage",
            "inputs": {
                "positive": ["94", 0],
                "negative": ["94", 1],
                "shape_latent": ["23", 0],
            },
        },
        "12": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["319", 0],
                "positive": ["98", 0],
                "negative": ["98", 1],
                "latent_image": ["98", 2],
                "seed": int(seed) + 1,
                "steps": 12,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "93": {
            "class_type": "VaeDecodeTextureTrellis",
            "inputs": {
                "samples": ["12", 0],
                "vae": ["118", 0],
                "shape_subdivides": ["92", 1],
            },
        },
        "241": {
            "class_type": "RemeshMesh",
            "inputs": {
                "mesh": ["92", 0],
                "resolution": remesh_res,
                # ComfyUI 0.46 defines sign_mode as a DynamicCombo. Its mode-specific
                # fields must be nested in this value; top-level qef/fill are ignored.
                "sign_mode": {"sign_mode": "solid", "fill": 20.0, "qef": False},
                "band": 1,
                "project_back": 0,
                "fix_poles": False,
                "smooth_iters": 12,
                "drop_small_components": 0.015,
                "precluster_max_verts": 5000000,
            },
        },
        "186": {
            "class_type": "DecimateMesh",
            "inputs": {
                "mesh": ["241", 0],
                "target_face_count": int(target_tris),
                "placement_mode": "midpoint",
            },
        },
        "238": {
            "class_type": "MeshSmoothNormals",
            "inputs": {"mesh": ["186", 0], "crease_angle": 180.0},
        },
        "196": {
            "class_type": "UnwrapMesh",
            "inputs": {
                "mesh": ["238", 0],
                "segmenter": "pec",
                "resolution": int(texture_size),
                "padding": 2,
                "weld_distance": 0.0002,
            },
        },
        "147": {
            "class_type": "BakeTextureFromVoxel",
            "inputs": {
                "mesh": ["196", 0],
                "voxel_colors": ["93", 0],
                "reference_mesh": ["92", 0],
                "texture_size": int(texture_size),
            },
        },
        "224": {
            "class_type": "BakeNormalMapFromMesh",
            "inputs": {
                "low_poly": ["196", 0],
                "high_poly": ["241", 0],
                "resolution": int(texture_size),
                "cage_distance": 0.05,
                "ignore_backfaces": True,
            },
        },
        "233": {
            "class_type": "BakeAmbientOcclusion",
            "inputs": {
                "low_poly": ["196", 0],
                "high_poly": ["241", 0],
                "resolution": int(texture_size),
                "samples": 32,
                "max_distance": 0.71,
                "strength": 1.0,
                "bias": 0.01,
            },
        },
        "210": {
            "class_type": "ApplyTextureToMesh",
            "inputs": {
                "mesh": ["196", 0],
                "base_color": ["147", 0],
                "metallic": ["147", 1],
                "roughness": ["147", 2],
                "occlusion": ["233", 0],
                "normal_map": ["224", 0],
            },
        },
        "260": {"class_type": "MeshSmoothNormals", "inputs": {"mesh": ["210", 0], "crease_angle": 180.0}},
        "285": {"class_type": "MeshToFile3D", "inputs": {"mesh": ["260", 0]}},
        "372": {
            "class_type": "Save3DAdvanced",
            "inputs": {
                "model_3d": ["285", 0],
                "filename_prefix": "3d/RoForge_Pixal3D",
                "viewport_state": "",
                "width": 1024,
                "height": 1024,
            },
        },
    }


def run_comfy_pixal3d_multiview(
    view_images: Dict[str, Image.Image],
    out_glb_path: Path,
    comfy_url: str = "http://127.0.0.1:8188",
    target_tris: int = 7500,
    texture_size: int = 1024,
    seed: int = 42,
    timeout_sec: int = 900,
) -> Path:
    """Upload 2-4 views to local ComfyUI, execute Pixal3D Multi-View (6 GB VRAM config), save GLB."""
    base = comfy_url.rstrip("/")
    client_id = str(uuid.uuid4())
    uploaded_names: Dict[str, str] = {}

    with httpx.Client(timeout=60.0) as client:
        for vname, pil_img in view_images.items():
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            fname = f"roforge_{client_id[:8]}_{vname}.png"
            resp = client.post(
                f"{base}/upload/image",
                files={"image": (fname, buf.getvalue(), "image/png")},
                data={"overwrite": "true"},
            )
            resp.raise_for_status()
            uploaded_names[vname] = resp.json().get("name", fname)

        prompt_graph = build_pixal3d_mv_api_prompt(
            uploaded_filenames=uploaded_names,
            target_tris=target_tris,
            texture_size=texture_size,
            voxel_res=512,
            seed=seed,
        )
        q_resp = client.post(
            f"{base}/prompt",
            json={"prompt": prompt_graph, "client_id": client_id},
        )
        if q_resp.is_error:
            try:
                error_detail = q_resp.json()
            except ValueError:
                error_detail = q_resp.text
            raise RuntimeError(f"ComfyUI rejected the Pixal3D workflow: {error_detail}")
        prompt_id = q_resp.json()["prompt_id"]

    # Poll /history/{prompt_id} until Save3DAdvanced finishes
    deadline = time.time() + timeout_sec
    with httpx.Client(timeout=30.0) as client:
        while time.time() < deadline:
            h_resp = client.get(f"{base}/history/{prompt_id}")
            if h_resp.status_code == 200:
                hist = h_resp.json()
                if prompt_id in hist:
                    outputs = hist[prompt_id].get("outputs", {})
                    for node_out in outputs.values():
                        for key in ("3d", "result", "model_3d", "gltf", "meshes"):
                            items = node_out.get(key, [])
                            if isinstance(items, list) and items:
                                item = items[0]
                                filename = item.get("filename")
                                subfolder = item.get("subfolder", "")
                                ftype = item.get("type", "output")
                                if filename:
                                    dl = client.get(
                                        f"{base}/view",
                                        params={"filename": filename, "subfolder": subfolder, "type": ftype},
                                    )
                                    dl.raise_for_status()
                                    out_glb_path.write_bytes(dl.content)
                                    return out_glb_path
                    raise RuntimeError("ComfyUI finished prompt, but no 3D GLB artifact was found in outputs.")
            time.sleep(2.0)

    raise TimeoutError(f"ComfyUI Pixal3D Multi-View timed out after {timeout_sec}s.")
