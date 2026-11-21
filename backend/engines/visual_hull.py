"""Instant Local Multi-View Visual-Hull + Smooth SDF Reconstruction Engine.
Works on ANY machine (0 GB VRAM / pure CPU) as an instant previewer or offline low-poly sculptor,
using 2–4 turnaround views (front, left, back, right) in right-handed glTF/Roblox coordinates (+X Right, +Y Up, +Z Front).
"""

from __future__ import annotations

from typing import Dict

import numpy as np
from scipy import ndimage
from skimage import measure
import trimesh


def reconstruct_multiview_visual_hull(
    views_rgba: Dict[str, np.ndarray],
    grid_res: int = 104,
    roundness: float = 0.38,
    taubin_iters: int = 12,
) -> trimesh.Trimesh:
    """Carve a smooth 3D mesh from 2–4 height-normalized RGBA turnaround views."""
    R = int(np.clip(grid_res, 48, 160))

    def get_sil_and_edt(view_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        alpha = view_arr[:, :, 3]
        # Resize alpha to (R, R)
        from PIL import Image
        a_res = np.array(
            Image.fromarray(alpha, mode="L").resize((R, R), Image.Resampling.BILINEAR),
            dtype=np.float32,
        ) / 255.0
        # Row 0 in image is +Y (top), row R-1 is -Y (bottom) -> flip row so index 0 = -Y, R-1 = +Y
        a_up = a_res[::-1, :]  # shape (Y, U_horiz)
        mask = a_up > 0.25
        if not np.any(mask):
            return np.ones((R, R), dtype=bool), np.ones((R, R), dtype=np.float32)
        edt_in = ndimage.distance_transform_edt(mask).astype(np.float32)
        edt_out = ndimage.distance_transform_edt(~mask).astype(np.float32)
        sdf2d = edt_in - edt_out  # positive inside, negative outside
        # Normalize interior depth per scanline so thin parts vs thick parts scale naturally
        row_max = np.maximum(edt_in.max(axis=1, keepdims=True), 1.0)
        norm_in = np.clip(edt_in / row_max, 0.0, 1.0)
        return mask, norm_in

    has_front = "front" in views_rgba
    has_back = "back" in views_rgba
    has_right = "right" in views_rgba
    has_left = "left" in views_rgba

    # Front (+Z): horiz col -> +X (index 0..-X to R-1..+X)
    # Back (-Z): horiz col -> -X, so flip horiz col to align with +X!
    masks_xy = []
    norms_xy = []
    if has_front:
        m, n = get_sil_and_edt(views_rgba["front"])
        masks_xy.append(m)
        norms_xy.append(n)
    if has_back:
        m, n = get_sil_and_edt(views_rgba["back"])
        masks_xy.append(m[:, ::-1])
        norms_xy.append(n[:, ::-1])

    # Left (-X): horiz col -> +Z (index 0..-Z to R-1..+Z)
    # Right (+X): horiz col -> -Z, so flip horiz col to align with +Z!
    masks_zy = []
    norms_zy = []
    if has_left:
        m, n = get_sil_and_edt(views_rgba["left"])
        masks_zy.append(m)
        norms_zy.append(n)
    if has_right:
        m, n = get_sil_and_edt(views_rgba["right"])
        masks_zy.append(m[:, ::-1])
        norms_zy.append(n[:, ::-1])

    if masks_xy:
        # Union if slight pose jitter, intersection if strict; soft average of normalized interior keeps thin blades intact
        mask_xy = np.logical_or.reduce(masks_xy) if len(masks_xy) == 1 else (
            np.mean([m.astype(np.float32) for m in masks_xy], axis=0) >= 0.5
        )
        norm_xy = np.mean(norms_xy, axis=0)
    else:
        mask_xy = np.ones((R, R), dtype=bool)
        norm_xy = np.ones((R, R), dtype=np.float32)

    if masks_zy:
        mask_zy = np.logical_or.reduce(masks_zy) if len(masks_zy) == 1 else (
            np.mean([m.astype(np.float32) for m in masks_zy], axis=0) >= 0.5
        )
        norm_zy = np.mean(norms_zy, axis=0)
    else:
        # If user only gave Front (+ Back) without side views, infer proportional depth profile from XY thickness!
        edt_xy = ndimage.distance_transform_edt(mask_xy).astype(np.float32)
        half_thick = np.clip(edt_xy / max(float(edt_xy.max()), 1.0), 0.0, 1.0)
        z_lin = np.abs(np.linspace(-1.0, 1.0, R, dtype=np.float32))[None, None, :]
        # Volume indexed as (X, Y, Z)
        n_xy_T = np.transpose(half_thick, (1, 0))[:, :, None]  # (X, Y, 1)
        occ = (n_xy_T > 0.02) & (z_lin <= n_xy_T * 0.65)
        masks_zy = None

    if masks_zy is not None:
        # Convert (Y, X) -> (X, Y, 1) and (Y, Z) -> (1, Y, Z)
        m_xy_3d = np.transpose(mask_xy, (1, 0))[:, :, None]
        m_zy_3d = np.transpose(mask_zy, (1, 0))[None, :, :]
        n_xy_3d = np.transpose(norm_xy, (1, 0))[:, :, None]
        n_zy_3d = np.transpose(norm_zy, (1, 0))[None, :, :]

        hull_box = m_xy_3d & m_zy_3d
        # Elliptical chamfer: corners where both n_xy and n_zy are very close to silhouette edge round smoothly
        r_blend = float(np.clip(roundness, 0.0, 0.85))
        if r_blend > 0.01:
            dx = 1.0 - n_xy_3d
            dz = 1.0 - n_zy_3d
            ellip_dist = np.sqrt(dx * dx + dz * dz)
            thresh = 1.0 + (1.0 - r_blend) * 0.42
            occ = hull_box & (ellip_dist <= thresh)
            # Never erase thin features (like blades or horns <= 4 voxels wide)
            if np.sum(occ) < 0.35 * max(np.sum(hull_box), 1):
                occ = hull_box
        else:
            occ = hull_box

    # Pad volume with 2 empty voxels on all 6 borders so marching_cubes produces a closed manifold shell
    vol = np.pad(occ.astype(np.float32), pad_width=3, mode="constant", constant_values=0.0)
    sdf = ndimage.gaussian_filter(vol, sigma=1.05)

    if sdf.max() <= 0.25:
        return trimesh.creation.icosphere(subdivisions=3, radius=1.0)

    verts, faces, normals, _ = measure.marching_cubes(sdf, level=0.42)
    # Map voxel indices back to centered right-handed coordinates [-0.5, +0.5]
    # Note: marching_cubes face winding in (X, Y, Z) with decreasing level needs normal check
    span = float(R + 6 - 1)
    verts_centered = (verts / span) - 0.5

    mesh = trimesh.Trimesh(vertices=verts_centered, faces=faces, process=True)
    mesh.fix_normals()

    if taubin_iters > 0 and len(mesh.faces) > 50:
        try:
            trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=taubin_iters)
        except Exception:
            pass

    mesh.fix_normals()
    return mesh
