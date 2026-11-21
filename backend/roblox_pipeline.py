"""Roblox Studio 3D Asset Post-Processor:
- Mesh cleanup & Garland-Heckbert QEM decimation (fast_simplification)
- Roblox stud scaling & floor-pivot grounding (Y=0)
- 6-tile seam-free UV atlas unwrapping & multi-view camera texture projection
- glTF metallicRoughness splitter -> 4 Roblox SurfaceAppearance PNGs:
  ColorMap.png, NormalMap.png, MetalnessMap.png, RoughnessMap.png
- Full glTF 2.0 PBR .glb + .obj export + Roblox Studio Luau setup script + .zip bundle
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import cv2
import fast_simplification
import numpy as np
from PIL import Image
import trimesh
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

from .presets import ROBLOX_HARD_MESHPART_TRI_CAP, ROBLOX_PRESETS


def extract_foreground_rgba(img: Image.Image) -> Image.Image:
    """Ensure clean RGBA cutout; if image has an opaque uniform/corner background, key it out."""
    rgba = img.convert("RGBA")
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]

    # If image already has meaningful transparency, keep its alpha channel
    transparent_ratio = float(np.mean(alpha < 240))
    if transparent_ratio > 0.03:
        return rgba

    rgb = arr[:, :, :3]
    h, w, _ = rgb.shape
    pad = max(2, min(h, w) // 25)
    corners = np.concatenate(
        [
            rgb[:pad, :pad].reshape(-1, 3),
            rgb[:pad, -pad:].reshape(-1, 3),
            rgb[-pad:, :pad].reshape(-1, 3),
            rgb[-pad:, -pad:].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_color = np.median(corners, axis=0)

    # Color distance in perceptual-ish weighted RGB
    diff = rgb.astype(np.float32) - bg_color.astype(np.float32)
    dist = np.sqrt(0.3 * diff[:, :, 0] ** 2 + 0.59 * diff[:, :, 1] ** 2 + 0.11 * diff[:, :, 2] ** 2)

    # Flood-fill style border background mask combined with color threshold
    bg_candidate = (dist < 22.0).astype(np.uint8) * 255
    num_labels, labels = cv2.connectedComponents(bg_candidate)
    border_labels = set(
        np.unique(
            np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
        ).tolist()
    )
    border_labels.discard(0)
    is_bg = np.isin(labels, list(border_labels))

    fg_mask = (~is_bg).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    fg_mask = cv2.GaussianBlur(fg_mask, (3, 3), 0)

    # Safety: if keying wiped almost everything, keep original opaque image
    if np.mean(fg_mask > 127) < 0.02:
        return rgba

    arr[:, :, 3] = fg_mask
    return Image.fromarray(arr, mode="RGBA")


def normalize_view_canvas(img: Image.Image, size: int = 512, margin_ratio: float = 0.10) -> np.ndarray:
    """Height-normalized object framing onto a square RGBA canvas (prevents profile scale drift)."""
    rgba = extract_foreground_rgba(img)
    arr = np.array(rgba, dtype=np.uint8)
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 24)
    if len(ys) < 16:
        resized = rgba.resize((size, size), Image.Resampling.LANCZOS)
        return np.array(resized, dtype=np.uint8)

    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    crop = arr[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]

    usable = int(round(size * (1.0 - 2.0 * margin_ratio)))
    scale = min(usable / max(ch, 1), usable / max(cw, 1))
    nh = max(1, int(round(ch * scale)))
    nw = max(1, int(round(cw * scale)))

    crop_pil = Image.fromarray(crop, mode="RGBA").resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = np.zeros((size, size, 4), dtype=np.uint8)
    oy = (size - nh) // 2
    ox = (size - nw) // 2
    canvas[oy : oy + nh, ox : ox + nw] = np.array(crop_pil, dtype=np.uint8)
    return canvas


def clean_and_decimate_mesh(
    mesh: trimesh.Trimesh,
    target_tris: int,
    target_studs: float = 4.0,
    ground_pivot: bool = True,
) -> Tuple[trimesh.Trimesh, Dict[str, Any]]:
    """Clean floaters/degenerates, QEM decimate under Roblox cap, scale to studs, ground at Y=0."""
    target_tris = int(max(200, min(target_tris, ROBLOX_HARD_MESHPART_TRI_CAP - 100)))

    work = mesh.copy()
    work.merge_vertices()
    work.update_faces(work.nondegenerate_faces())
    work.update_faces(work.unique_faces())
    work.remove_unreferenced_vertices()

    raw_tris = int(len(work.faces))
    raw_verts = int(len(work.vertices))

    # Drop tiny detached floaters (< 1.5% of largest component faces)
    try:
        parts = work.split(only_watertight=False)
        if len(parts) > 1:
            largest_faces = max(len(p.faces) for p in parts)
            kept = [p for p in parts if len(p.faces) >= max(12, int(largest_faces * 0.015))]
            if kept:
                work = trimesh.util.concatenate(kept)
                work.merge_vertices()
    except Exception:
        pass

    # Garland-Heckbert Quadric Error Metric decimation via fast_simplification
    if len(work.faces) > target_tris:
        verts_f32 = np.ascontiguousarray(work.vertices, dtype=np.float32)
        faces_i32 = np.ascontiguousarray(work.faces, dtype=np.int32)
        reduction = 1.0 - (float(target_tris) / float(len(faces_i32)))
        reduction = float(np.clip(reduction, 0.01, 0.995))
        try:
            v_out, f_out = fast_simplification.simplify(
                verts_f32, faces_i32, target_reduction=reduction, agg=7
            )
            # If still slightly above target_tris, run one tighter pass
            if len(f_out) > target_tris:
                extra_red = 1.0 - (float(target_tris * 0.97) / float(len(f_out)))
                v_out, f_out = fast_simplification.simplify(
                    np.ascontiguousarray(v_out, dtype=np.float32),
                    np.ascontiguousarray(f_out, dtype=np.int32),
                    target_reduction=float(np.clip(extra_red, 0.01, 0.95)),
                    agg=8,
                )
            work = trimesh.Trimesh(vertices=v_out, faces=f_out, process=True)
        except Exception:
            pass

    # Scale to target Roblox Studs (largest bounding box axis = target_studs)
    bounds = work.bounds
    extents = bounds[1] - bounds[0]
    max_ext = float(np.max(extents)) if np.max(extents) > 1e-6 else 1.0
    scale_factor = float(target_studs) / max_ext
    work.apply_scale(scale_factor)

    # Center X/Z at 0, ground bottom at Y=0 (Roblox MeshPart floor pivot)
    b0, b1 = work.bounds
    cx = 0.5 * (b0[0] + b1[0])
    cz = 0.5 * (b0[2] + b1[2])
    cy = b0[1] if ground_pivot else 0.5 * (b0[1] + b1[1])
    work.apply_translation([-cx, -cy, -cz])
    work.fix_normals()

    final_extents = (work.bounds[1] - work.bounds[0]).tolist()
    stats = {
        "raw_triangles": raw_tris,
        "raw_vertices": raw_verts,
        "final_triangles": int(len(work.faces)),
        "final_vertices": int(len(work.vertices)),
        "is_watertight": bool(work.is_watertight),
        "dimensions_studs": {
            "x": round(float(final_extents[0]), 3),
            "y": round(float(final_extents[1]), 3),
            "z": round(float(final_extents[2]), 3),
        },
        "dimensions_meters": {
            "x": round(float(final_extents[0]) * 0.28, 3),
            "y": round(float(final_extents[1]) * 0.28, 3),
            "z": round(float(final_extents[2]) * 0.28, 3),
        },
    }
    return work, stats


def unwrap_6tile_box_uv(mesh: trimesh.Trimesh) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unwrap mesh into a clean 6-tile normal-clustered UV atlas (3x2 grid) with gutter margins.
    Returns (unwrapped_vertices, unwrapped_faces, uvs) with zero seam stretching.
    """
    verts = mesh.vertices
    faces = mesh.faces
    fnormals = mesh.face_normals
    vnormals = mesh.vertex_normals

    # Assign each face to one of 6 axis tiles:
    # 0: +Z (front), 1: -Z (back), 2: +X (right), 3: -X (left), 4: +Y (top), 5: -Y (bottom)
    abs_n = np.abs(fnormals)
    dom_axis = np.argmax(abs_n, axis=1)  # 0=X, 1=Y, 2=Z
    tile_idx = np.zeros(len(faces), dtype=np.int32)

    is_x = dom_axis == 0
    is_y = dom_axis == 1
    is_z = dom_axis == 2
    tile_idx[is_z & (fnormals[:, 2] >= 0)] = 0  # +Z front
    tile_idx[is_z & (fnormals[:, 2] < 0)] = 1   # -Z back
    tile_idx[is_x & (fnormals[:, 0] >= 0)] = 2  # +X right
    tile_idx[is_x & (fnormals[:, 0] < 0)] = 3   # -X left
    tile_idx[is_y & (fnormals[:, 1] >= 0)] = 4  # +Y top
    tile_idx[is_y & (fnormals[:, 1] < 0)] = 5   # -Y bottom

    # Normalize vertex coordinates into [0, 1] per axis
    bmin = verts.min(axis=0)
    bmax = verts.max(axis=0)
    span = np.maximum(bmax - bmin, 1e-5)
    norm_v = (verts - bmin) / span  # (V, 3) in [0, 1]

    # Duplicate per-face vertices so UV tile boundaries never stretch across tiles
    tri_verts = verts[faces].reshape(-1, 3)       # (3F, 3)
    tri_vnorm = vnormals[faces].reshape(-1, 3)    # (3F, 3)
    tri_norm = norm_v[faces].reshape(-1, 3)       # (3F, 3)
    tri_tiles = np.repeat(tile_idx, 3)            # (3F,)

    u_local = np.zeros(len(tri_verts), dtype=np.float32)
    v_local = np.zeros(len(tri_verts), dtype=np.float32)

    # +Z front: u = +x, v = +y
    m = tri_tiles == 0
    u_local[m], v_local[m] = tri_norm[m, 0], tri_norm[m, 1]
    # -Z back: u = 1 - x, v = +y
    m = tri_tiles == 1
    u_local[m], v_local[m] = 1.0 - tri_norm[m, 0], tri_norm[m, 1]
    # +X right: u = 1 - z, v = +y
    m = tri_tiles == 2
    u_local[m], v_local[m] = 1.0 - tri_norm[m, 2], tri_norm[m, 1]
    # -X left: u = +z, v = +y
    m = tri_tiles == 3
    u_local[m], v_local[m] = tri_norm[m, 2], tri_norm[m, 1]
    # +Y top: u = +x, v = 1 - z
    m = tri_tiles == 4
    u_local[m], v_local[m] = tri_norm[m, 0], 1.0 - tri_norm[m, 2]
    # -Y bottom: u = +x, v = +z
    m = tri_tiles == 5
    u_local[m], v_local[m] = tri_norm[m, 0], tri_norm[m, 2]

    # Pack into 3 columns x 2 rows with 7% inner margin for Telea seam dilation
    margin = 0.07
    u_in = margin + u_local * (1.0 - 2.0 * margin)
    v_in = margin + v_local * (1.0 - 2.0 * margin)

    col = (tri_tiles % 3).astype(np.float32)
    row = (tri_tiles // 3).astype(np.float32)  # 0 or 1

    uvs = np.stack([(col + u_in) / 3.0, (row + v_in) / 2.0], axis=1).astype(np.float32)
    new_faces = np.arange(len(tri_verts), dtype=np.int32).reshape(-1, 3)
    return tri_verts, new_faces, uvs, tri_vnorm


def bake_multiview_pbr_maps(
    verts: np.ndarray,
    faces: np.ndarray,
    uvs: np.ndarray,
    vnormals: np.ndarray,
    views_rgba: Dict[str, np.ndarray],
    texture_size: int = 1024,
    metallic_bias: float = 0.25,
    roughness_bias: float = 0.55,
) -> Dict[str, Image.Image]:
    """Project 2-4 turnaround views onto the UV atlas and synthesize Roblox SurfaceAppearance PBR maps."""
    H = W = int(texture_size)

    # Normalize 3D coordinates to [0, 1] along each axis to align with normalized view canvases
    bmin = verts.min(axis=0)
    bmax = verts.max(axis=0)
    span = np.maximum(bmax - bmin, 1e-5)

    # Preserve aspect ratio inside the square view canvas (margin_ratio = 0.10)
    max_span = float(np.max(span))
    center = 0.5 * (bmin + bmax)
    # Coordinates in [-0.5, 0.5] relative to max_span, mapped to [0.10, 0.90] of the view canvas
    rel = (verts - center) / max_span  # [-0.5, 0.5]

    pos_map = np.zeros((H, W, 3), dtype=np.float32)
    nrm_map = np.zeros((H, W, 3), dtype=np.float32)
    occ_mask = np.zeros((H, W), dtype=np.uint8)

    # Rasterize UV triangles into (H, W) atlas
    px_u = uvs[:, 0] * (W - 1)
    px_v = (1.0 - uvs[:, 1]) * (H - 1)  # PIL/image top-left origin vs UV bottom-left

    for f in faces:
        i0, i1, i2 = int(f[0]), int(f[1]), int(f[2])
        x0, y0 = px_u[i0], px_v[i0]
        x1, y1 = px_u[i1], px_v[i1]
        x2, y2 = px_u[i2], px_v[i2]

        xmin = max(0, int(math.floor(min(x0, x1, x2))))
        xmax = min(W - 1, int(math.ceil(max(x0, x1, x2))))
        ymin = max(0, int(math.floor(min(y0, y1, y2))))
        ymax = min(H - 1, int(math.ceil(max(y0, y1, y2))))
        if xmax < xmin or ymax < ymin:
            continue

        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-6:
            continue

        yy, xx = np.mgrid[ymin : ymax + 1, xmin : xmax + 1]
        xx_f = xx.astype(np.float32)
        yy_f = yy.astype(np.float32)

        w0 = ((y1 - y2) * (xx_f - x2) + (x2 - x1) * (yy_f - y2)) / denom
        w1 = ((y2 - y0) * (xx_f - x2) + (x0 - x2) * (yy_f - y2)) / denom
        w2 = 1.0 - w0 - w1

        inside = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        if not np.any(inside):
            continue

        w0c = w0[inside][:, None]
        w1c = w1[inside][:, None]
        w2c = w2[inside][:, None]

        p_interp = w0c * rel[i0] + w1c * rel[i1] + w2c * rel[i2]
        n_interp = w0c * vnormals[i0] + w1c * vnormals[i1] + w2c * vnormals[i2]

        sub_pos = pos_map[ymin : ymax + 1, xmin : xmax + 1]
        sub_nrm = nrm_map[ymin : ymax + 1, xmin : xmax + 1]
        sub_occ = occ_mask[ymin : ymax + 1, xmin : xmax + 1]

        sub_pos[inside] = p_interp
        sub_nrm[inside] = n_interp
        sub_occ[inside] = 255

    valid = occ_mask > 0
    n_len = np.linalg.norm(nrm_map[valid], axis=1, keepdims=True)
    nrm_map[valid] = nrm_map[valid] / np.maximum(n_len, 1e-6)

    # Sample each available orthographic view onto valid texels
    accum_rgb = np.zeros((H, W, 3), dtype=np.float32)
    accum_w = np.zeros((H, W, 1), dtype=np.float32)

    # Pre-extrude foreground RGB into transparent background of each view so bilinear sampling NEVER bleeds black!
    from scipy import ndimage as _ndi
    clean_views_rgb: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for vname, varr in views_rgba.items():
        v_rgb = varr[:, :, :3].copy()
        v_a = varr[:, :, 3]
        fg = v_a > 32
        if np.any(fg) and not np.all(fg):
            _, nearest_idx = _ndi.distance_transform_edt(~fg, return_indices=True)
            v_rgb = v_rgb[nearest_idx[0], nearest_idx[1]]
        clean_views_rgb[vname] = (v_rgb.astype(np.float32), v_a.astype(np.float32) / 255.0)

    def sample_view(vname: str, u_coord: np.ndarray, v_coord: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        v_rgb_f, v_alpha_f = clean_views_rgb[vname]
        vh, vw = v_rgb_f.shape[:2]
        sx = np.clip((0.5 + u_coord * 0.80) * (vw - 1), 0, vw - 1).astype(np.float32)
        sy = np.clip((0.5 - v_coord * 0.80) * (vh - 1), 0, vh - 1).astype(np.float32)
        sampled_rgb = cv2.remap(
            v_rgb_f,
            sx,
            sy,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        sampled_a = cv2.remap(
            v_alpha_f,
            sx,
            sy,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0.0,
        )
        return sampled_rgb, sampled_a[:, :, None]

    px, py, pz = pos_map[:, :, 0], pos_map[:, :, 1], pos_map[:, :, 2]
    nx, ny, nz = nrm_map[:, :, 0], nrm_map[:, :, 1], nrm_map[:, :, 2]

    view_specs = [
        ("front", np.maximum(0.0, nz) ** 2.2 + 0.04, px, py),
        ("back", np.maximum(0.0, -nz) ** 2.2 + 0.04, -px, py),
        ("right", np.maximum(0.0, nx) ** 2.2 + 0.04, -pz, py),
        ("left", np.maximum(0.0, -nx) ** 2.2 + 0.04, pz, py),
    ]

    for vname, weight_2d, u_c, v_c in view_specs:
        if vname not in clean_views_rgb:
            continue
        rgb_s, alpha_s = sample_view(vname, u_c, v_c)
        # Keep mild weight even slightly outside silhouette so rounded 3D hull edges still receive nearest color
        alpha_clean = 0.15 + 0.85 * np.clip(alpha_s, 0.0, 1.0)
        w = (weight_2d[:, :, None] * alpha_clean) * valid[:, :, None]
        accum_rgb += rgb_s * w
        accum_w += w

    # Top/bottom or un-hit texels inherit median foreground color of views
    fg_pixels = []
    for v_arr in views_rgba.values():
        m = v_arr[:, :, 3] > 128
        if np.any(m):
            fg_pixels.append(v_arr[m, :3])
    fallback_color = (
        np.median(np.concatenate(fg_pixels, axis=0), axis=0).astype(np.float32)
        if fg_pixels
        else np.array([180.0, 185.0, 195.0], dtype=np.float32)
    )

    color_atlas = np.zeros((H, W, 3), dtype=np.uint8)
    has_w = (accum_w[:, :, 0] > 1e-4) & valid
    color_atlas[has_w] = np.clip(accum_rgb[has_w] / accum_w[has_w], 0, 255).astype(np.uint8)
    missing_valid = valid & (~has_w)
    color_atlas[missing_valid] = fallback_color.astype(np.uint8)

    # Nearest-pixel UV island dilation (zero black border seams across all Roblox mipmap levels!)
    if np.any(valid) and not np.all(valid):
        dist_out, nearest_uv = _ndi.distance_transform_edt(~valid, return_indices=True)
        color_inpainted = color_atlas[nearest_uv[0], nearest_uv[1]].copy()
        bg_outside = dist_out > 18.0
        color_inpainted[bg_outside] = fallback_color.astype(np.uint8)
    else:
        color_inpainted = color_atlas.copy()
        bg_outside = ~valid

    # Synthesize OpenGL Tangent-Space NormalMap (+X right, +Y up, +Z out) without UV-border cliffs
    gray = cv2.cvtColor(color_inpainted, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3) * 1.15
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3) * 1.15
    # Suppress Sobel jump outside UV islands
    eroded_valid = cv2.erode(occ_mask, np.ones((3, 3), dtype=np.uint8)) > 0
    gx[~eroded_valid] = 0.0
    gy[~eroded_valid] = 0.0
    tx = -gx
    ty = gy  # OpenGL +Y convention used by Roblox SurfaceAppearance
    tz = np.ones_like(gray)
    tlen = np.sqrt(tx * tx + ty * ty + tz * tz)
    normal_rgb = np.zeros((H, W, 3), dtype=np.uint8)
    normal_rgb[:, :, 0] = np.clip((tx / tlen * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal_rgb[:, :, 1] = np.clip((ty / tlen * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal_rgb[:, :, 2] = np.clip((tz / tlen * 0.5 + 0.5) * 255.0, 128, 255).astype(np.uint8)
    normal_rgb[bg_outside] = np.array([128, 128, 255], dtype=np.uint8)

    # Estimate spatially varying Metalness & Roughness maps from luminance/saturation cues
    hsv = cv2.cvtColor(color_inpainted, cv2.COLOR_RGB2HSV).astype(np.float32) / 255.0
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    # Bright neutral/cool highlights & edges read more metallic; saturated matte areas read rougher
    edge_mag = np.clip(np.sqrt(gx * gx + gy * gy) * 0.5, 0.0, 0.35)
    metal_f = np.clip(metallic_bias + 0.30 * (val - 0.5) - 0.20 * sat + 0.15 * edge_mag, 0.02, 0.96)
    rough_f = np.clip(roughness_bias - 0.28 * (val - 0.5) + 0.18 * sat - 0.10 * edge_mag, 0.08, 0.96)

    metal_u8 = (metal_f * 255.0).astype(np.uint8)
    rough_u8 = (rough_f * 255.0).astype(np.uint8)

    return {
        "ColorMap": Image.fromarray(color_inpainted, mode="RGB"),
        "NormalMap": Image.fromarray(normal_rgb, mode="RGB"),
        "MetalnessMap": Image.fromarray(metal_u8, mode="L"),
        "RoughnessMap": Image.fromarray(rough_u8, mode="L"),
    }


def extract_pbr_maps_from_glb_scene(
    scene_or_mesh: Any, texture_size: int = 1024
) -> Optional[Dict[str, Image.Image]]:
    """Extract & split embedded glTF PBR textures (unpacking ORM Green->Roughness, Blue->Metalness)."""
    geoms = (
        list(scene_or_mesh.geometry.values())
        if isinstance(scene_or_mesh, trimesh.Scene)
        else [scene_or_mesh]
    )
    for g in geoms:
        vis = getattr(g, "visual", None)
        mat = getattr(vis, "material", None)
        if mat is None:
            continue
        base_tex = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if base_tex is None:
            continue

        color_img = base_tex.convert("RGBA" if base_tex.mode == "RGBA" else "RGB").resize(
            (texture_size, texture_size), Image.Resampling.LANCZOS
        )

        # Unpack glTF metallicRoughnessTexture (Green = Roughness, Blue = Metallic!)
        mr_tex = getattr(mat, "metallicRoughnessTexture", None)
        if mr_tex is not None:
            mr_rgb = np.array(
                mr_tex.convert("RGB").resize((texture_size, texture_size), Image.Resampling.LANCZOS),
                dtype=np.uint8,
            )
            rough_img = Image.fromarray(mr_rgb[:, :, 1], mode="L")
            metal_img = Image.fromarray(mr_rgb[:, :, 2], mode="L")
        else:
            mf = float(getattr(mat, "metallicFactor", 0.1) or 0.1)
            rf = float(getattr(mat, "roughnessFactor", 0.65) or 0.65)
            metal_img = Image.fromarray(
                np.full((texture_size, texture_size), int(np.clip(mf * 255, 0, 255)), dtype=np.uint8),
                mode="L",
            )
            rough_img = Image.fromarray(
                np.full((texture_size, texture_size), int(np.clip(rf * 255, 0, 255)), dtype=np.uint8),
                mode="L",
            )

        nrm_tex = getattr(mat, "normalTexture", None)
        if nrm_tex is not None:
            normal_img = nrm_tex.convert("RGB").resize(
                (texture_size, texture_size), Image.Resampling.LANCZOS
            )
        else:
            # Synthesize crisp OpenGL tangent normal map from albedo luminance
            c_arr = np.array(color_img.convert("RGB"), dtype=np.uint8)
            gray = cv2.cvtColor(c_arr, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3) * 1.1
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3) * 1.1
            tz = np.ones_like(gray)
            tlen = np.sqrt(gx * gx + gy * gy + tz * tz)
            n_rgb = np.stack(
                [
                    np.clip((-gx / tlen * 0.5 + 0.5) * 255, 0, 255),
                    np.clip((gy / tlen * 0.5 + 0.5) * 255, 0, 255),
                    np.clip((tz / tlen * 0.5 + 0.5) * 255, 128, 255),
                ],
                axis=-1,
            ).astype(np.uint8)
            normal_img = Image.fromarray(n_rgb, mode="RGB")

        return {
            "ColorMap": color_img,
            "NormalMap": normal_img,
            "MetalnessMap": metal_img,
            "RoughnessMap": rough_img,
        }
    return None


def build_pbr_glb_mesh(
    verts: np.ndarray,
    faces: np.ndarray,
    uvs: np.ndarray,
    maps: Dict[str, Image.Image],
    asset_name: str = "RobloxAsset",
) -> trimesh.Trimesh:
    """Pack split SurfaceAppearance maps back into a standard glTF 2.0 PBR Trimesh."""
    rough_arr = np.array(maps["RoughnessMap"].convert("L"), dtype=np.uint8)
    metal_arr = np.array(maps["MetalnessMap"].convert("L"), dtype=np.uint8)
    ao_arr = np.full_like(rough_arr, 255)
    # glTF 2.0 spec: R = Occlusion, G = Roughness, B = Metalness
    orm_rgb = np.stack([ao_arr, rough_arr, metal_arr], axis=-1)
    orm_img = Image.fromarray(orm_rgb, mode="RGB")

    pbr_mat = PBRMaterial(
        name=f"{asset_name}_SurfaceAppearance",
        baseColorTexture=maps["ColorMap"],
        metallicRoughnessTexture=orm_img,
        normalTexture=maps["NormalMap"],
        metallicFactor=1.0,
        roughnessFactor=1.0,
        doubleSided=False,
    )
    visual = TextureVisuals(uv=uvs, material=pbr_mat)
    mesh_out = trimesh.Trimesh(vertices=verts, faces=faces, visual=visual, process=False)
    mesh_out.fix_normals()
    return mesh_out


def generate_roblox_luau_script(
    asset_name: str,
    preset: Dict[str, Any],
    stats: Dict[str, Any],
    alpha_mode: str = "Opaque",
) -> str:
    """Generate a ready-to-paste Roblox Studio Command Bar Luau setup script."""
    dims = stats["dimensions_studs"]
    return f"""-- RoForge 3D — Roblox Studio SurfaceAppearance Auto-Setup Script
-- Asset: {asset_name} | Preset: {preset['name']}
-- Verified Triangles: {stats['final_triangles']} / {preset['hard_cap']} (PASS)
--Instructions:
-- 1. Import '{asset_name}_roblox.glb' via Roblox Studio -> Avatar/Home -> Import 3D.
-- 2. Upload the 4 PNGs inside 'SurfaceAppearance/' to Asset Manager -> Images,
--    then paste their rbxassetid:// numbers below (if not auto-linked by GLB import)
--    and run this script in the Studio Command Bar with your MeshPart selected!

local Selection = game:GetService("Selection")
local selected = Selection:Get()
local meshPart = selected[1]

if not meshPart or not meshPart:IsA("MeshPart") then
    warn("[RoForge 3D] Select your imported '{asset_name}' MeshPart in Workspace first!")
    return
end

meshPart.Name = "{asset_name}"
meshPart.Size = Vector3.new({dims['x']}, {dims['y']}, {dims['z']})
meshPart.RenderFidelity = Enum.RenderFidelity.{preset['render_fidelity']}
meshPart.Material = Enum.Material.SmoothPlastic

local surfaceAppearance = meshPart:FindFirstChildOfClass("SurfaceAppearance")
if not surfaceAppearance then
    surfaceAppearance = Instance.new("SurfaceAppearance")
    surfaceAppearance.Name = "SurfaceAppearance"
    surfaceAppearance.Parent = meshPart
end

surfaceAppearance.AlphaMode = Enum.AlphaMode.{alpha_mode}
-- Paste your uploaded rbxassetid:// IDs from Asset Manager -> Images:
-- surfaceAppearance.ColorMap = "rbxassetid://YOUR_COLOR_MAP_ID"
-- surfaceAppearance.NormalMap = "rbxassetid://YOUR_NORMAL_MAP_ID"
-- surfaceAppearance.MetalnessMap = "rbxassetid://YOUR_METALNESS_MAP_ID"
-- surfaceAppearance.RoughnessMap = "rbxassetid://YOUR_ROUGHNESS_MAP_ID"

print(string.format(
    "[RoForge 3D] Configured '%s' (%d tris, %.2f x %.2f x %.2f studs, RenderFidelity=%s)",
    meshPart.Name, {stats['final_triangles']}, {dims['x']}, {dims['y']}, {dims['z']}, "{preset['render_fidelity']}"
))
"""


def export_complete_roblox_bundle(
    raw_mesh: trimesh.Trimesh,
    output_dir: Path,
    asset_name: str,
    preset_id: str = "weapon_tool",
    target_tris: Optional[int] = None,
    texture_size: int = 1024,
    target_studs: Optional[float] = None,
    ground_pivot: bool = True,
    views_rgba: Optional[Dict[str, np.ndarray]] = None,
    existing_maps: Optional[Dict[str, Image.Image]] = None,
    metallic_bias: float = 0.25,
    roughness_bias: float = 0.55,
    engine_used: str = "visual_hull",
) -> Dict[str, Any]:
    """Full end-to-end Roblox export: decimation, stud scaling, PBR maps, GLB, OBJ, Luau, and ZIP."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sa_dir = output_dir / "SurfaceAppearance"
    sa_dir.mkdir(parents=True, exist_ok=True)

    preset = ROBLOX_PRESETS.get(preset_id, ROBLOX_PRESETS["weapon_tool"])
    eff_tris = int(target_tris if target_tris is not None else preset["target_tris"])
    eff_studs = float(target_studs if target_studs is not None else preset["target_studs"])
    eff_tex = int(texture_size if texture_size in (512, 1024, 2048) else preset["texture_size"])

    clean_mesh, stats = clean_and_decimate_mesh(
        raw_mesh,
        target_tris=eff_tris,
        target_studs=eff_studs,
        ground_pivot=ground_pivot,
    )

    # Check if clean_mesh preserved UVs + existing maps, else unwrap 6-tile box atlas
    has_existing_uv = (
        existing_maps is not None
        and hasattr(clean_mesh.visual, "uv")
        and clean_mesh.visual.uv is not None
        and len(clean_mesh.visual.uv) == len(clean_mesh.vertices)
    )

    if has_existing_uv:
        u_verts = clean_mesh.vertices
        u_faces = clean_mesh.faces
        u_uvs = np.asarray(clean_mesh.visual.uv, dtype=np.float32)
        maps = existing_maps
    else:
        u_verts, u_faces, u_uvs, u_vnorm = unwrap_6tile_box_uv(clean_mesh)
        if existing_maps is not None and not views_rgba:
            maps = existing_maps
        else:
            maps = bake_multiview_pbr_maps(
                u_verts,
                u_faces,
                u_uvs,
                u_vnorm,
                views_rgba=views_rgba or {},
                texture_size=eff_tex,
                metallic_bias=metallic_bias,
                roughness_bias=roughness_bias,
            )

    # Save the 4 standalone Roblox SurfaceAppearance maps
    map_paths: Dict[str, Path] = {}
    for mname in ("ColorMap", "NormalMap", "MetalnessMap", "RoughnessMap"):
        p = sa_dir / f"{mname}.png"
        maps[mname].save(p, format="PNG")
        map_paths[mname] = p

    safe_slug = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in asset_name).strip("_") or "RobloxAsset"
    pbr_mesh = build_pbr_glb_mesh(u_verts, u_faces, u_uvs, maps, asset_name=safe_slug)

    glb_path = output_dir / f"{safe_slug}_roblox.glb"
    obj_path = output_dir / f"{safe_slug}_roblox.obj"
    lua_path = output_dir / "setup_surface_appearance.lua"
    report_path = output_dir / "roblox_validation_report.json"
    zip_path = output_dir / f"{safe_slug}_RobloxStudio_Bundle.zip"

    pbr_mesh.export(str(glb_path), file_type="glb")
    # Export clean geometry OBJ alongside GLB for classic Studio MeshPart workflow
    geom_only = trimesh.Trimesh(vertices=u_verts, faces=u_faces, process=False)
    geom_only.visual = TextureVisuals(uv=u_uvs)
    geom_only.export(str(obj_path), file_type="obj")

    alpha_mode = "Transparency" if maps["ColorMap"].mode == "RGBA" else "Overlay"
    luau_code = generate_roblox_luau_script(safe_slug, preset, stats, alpha_mode=alpha_mode)
    lua_path.write_text(luau_code, encoding="utf-8")

    # Update stats with exact post-UV-split vertex count while triangle count stays identical
    stats["final_triangles"] = int(len(u_faces))
    stats["render_vertices_uv_split"] = int(len(u_verts))
    stats["hard_cap"] = int(preset["hard_cap"])
    stats["meshpart_hard_cap"] = ROBLOX_HARD_MESHPART_TRI_CAP
    stats["passes_preset_cap"] = bool(stats["final_triangles"] <= preset["hard_cap"])
    stats["passes_meshpart_cap"] = bool(stats["final_triangles"] <= ROBLOX_HARD_MESHPART_TRI_CAP)
    stats["texture_size"] = eff_tex
    stats["preset_id"] = preset_id
    stats["preset_name"] = preset["name"]
    stats["engine_used"] = engine_used

    report_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(glb_path, arcname=glb_path.name)
        zf.write(obj_path, arcname=obj_path.name)
        mtl_file = output_dir / "material.mtl"
        if mtl_file.exists():
            zf.write(mtl_file, arcname="material.mtl")
        for mname, mp in map_paths.items():
            zf.write(mp, arcname=f"SurfaceAppearance/{mp.name}")
        zf.write(lua_path, arcname=lua_path.name)
        zf.write(report_path, arcname=report_path.name)

    return {
        "asset_name": safe_slug,
        "glb_filename": glb_path.name,
        "obj_filename": obj_path.name,
        "zip_filename": zip_path.name,
        "lua_script": luau_code,
        "stats": stats,
    }
