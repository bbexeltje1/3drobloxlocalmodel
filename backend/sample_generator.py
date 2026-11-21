"""Generates 4 built-in 3D-consistent 4-view RGBA turnaround sheets (`front`, `left`, `back`, `right`)
for instant testing of the Roblox Multi-View Asset Creator:
1. dragon_helm   — Crimson Dragon Knight Helm (UGC Rigid Accessory, ≤3,600 tris)
2. cyber_katana  — Cyber Neon Tech-Blade (Weapon / Held Tool, ≤7,500 tris)
3. treasure_chest— Gilded Pirate Chest (Repeated Map Prop, ≤2,400 tris)
4. mecha_core    — Aether Mecha Sentinel Drone (Hero MeshPart, ≤15,000 tris)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Any, List, Tuple

import cv2
import numpy as np
from PIL import Image
import trimesh


SAMPLE_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "dragon_helm",
        "name": "Crimson Dragon Helm",
        "preset_id": "ugc_hat",
        "metallic_bias": 0.62,
        "roughness_bias": 0.35,
        "badge": "UGC Hat (≤3.6K Tris)",
        "description": "Horned crimson-and-gold knight helmet with T-visor and rear crest.",
    },
    {
        "id": "cyber_katana",
        "name": "Cyber Neon Tech-Sword",
        "preset_id": "weapon_tool",
        "metallic_bias": 0.72,
        "roughness_bias": 0.28,
        "badge": "Roblox Tool (≤7.5K Tris)",
        "description": "Broad sci-fi energy greatsword with octagonal guard, wrapped grip, and cyan edge.",
    },
    {
        "id": "treasure_chest",
        "name": "Gilded Pirate Chest",
        "preset_id": "map_prop",
        "metallic_bias": 0.32,
        "roughness_bias": 0.62,
        "badge": "Map Prop (≤2.4K Tris)",
        "description": "Domed oak treasure chest with forged iron bands, brass front lock, and side handles.",
    },
    {
        "id": "mecha_core",
        "name": "Aether Mecha Hover-Drone",
        "preset_id": "hero_meshpart",
        "metallic_bias": 0.68,
        "roughness_bias": 0.32,
        "badge": "Hero MeshPart (≤15K Tris)",
        "description": "Armored hover unit with front optic core, twin side thrusters, and dorsal stabilizer fins.",
    },
]


def _colored_part(mesh: trimesh.Trimesh, rgb: Tuple[int, int, int]) -> Tuple[trimesh.Trimesh, np.ndarray]:
    c = np.tile(np.array(rgb, dtype=np.uint8), (len(mesh.faces), 1))
    return mesh, c


def _build_dragon_helm_parts() -> List[Tuple[trimesh.Trimesh, np.ndarray]]:
    parts = []
    # Main dome
    dome = trimesh.creation.icosphere(subdivisions=3, radius=0.42)
    dome.apply_scale([0.92, 1.05, 1.0])
    parts.append(_colored_part(dome, (168, 28, 38)))

    # Lower cheek/jaw armor cylinder
    jaw = trimesh.creation.cylinder(radius=0.39, height=0.42, sections=28)
    jaw.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    jaw.apply_translation([0, -0.18, 0.02])
    parts.append(_colored_part(jaw, (140, 22, 32)))

    # Gold brow & curved crown arch
    r_arch = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
    crest = trimesh.creation.cylinder(radius=0.455, height=0.12, sections=28)
    crest.apply_transform(r_arch)
    crest.apply_translation([0, 0.04, 0.0])
    parts.append(_colored_part(crest, (238, 188, 54)))

    brow = trimesh.creation.box(extents=[0.82, 0.11, 0.26])
    brow.apply_translation([0, 0.08, 0.34])
    parts.append(_colored_part(brow, (242, 196, 65)))

    # Glowing dark-cyan T-visor on front (+Z)
    visor_h = trimesh.creation.box(extents=[0.56, 0.10, 0.14])
    visor_h.apply_translation([0, -0.03, 0.39])
    parts.append(_colored_part(visor_h, (32, 225, 245)))

    visor_v = trimesh.creation.box(extents=[0.12, 0.30, 0.14])
    visor_v.apply_translation([0, -0.16, 0.39])
    parts.append(_colored_part(visor_v, (24, 190, 220)))

    # Twin curved-style angled horns (+X and -X)
    for sx in (-1.0, 1.0):
        horn_base = trimesh.creation.cone(radius=0.13, height=0.58, sections=20)
        # Cone points +Z by default in trimesh -> rotate to point up (+Y) and outward (sx * +X) and slightly forward
        r1 = trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])
        r2 = trimesh.transformations.rotation_matrix(-sx * 0.58, [0, 0, 1])
        r3 = trimesh.transformations.rotation_matrix(0.22, [1, 0, 0])
        horn_base.apply_transform(r3 @ r2 @ r1)
        horn_base.apply_translation([sx * 0.34, 0.22, 0.05])
        parts.append(_colored_part(horn_base, (235, 222, 195)))

        ring = trimesh.creation.cylinder(radius=0.135, height=0.09, sections=20)
        ring.apply_transform(r3 @ r2 @ r1)
        ring.apply_translation([sx * 0.35, 0.24, 0.05])
        parts.append(_colored_part(ring, (238, 188, 54)))

    # Rear neck guard (-Z)
    back_plate = trimesh.creation.box(extents=[0.66, 0.32, 0.16])
    back_plate.apply_translation([0, -0.24, -0.36])
    parts.append(_colored_part(back_plate, (215, 165, 45)))
    return parts


def _build_cyber_katana_parts() -> List[Tuple[trimesh.Trimesh, np.ndarray]]:
    parts = []
    # Broad sci-fi blade body (thick enough to read crisply from all 4 angles)
    blade_core = trimesh.creation.box(extents=[0.20, 1.28, 0.09])
    blade_core.apply_translation([0.0, 0.34, 0.0])
    parts.append(_colored_part(blade_core, (46, 56, 74)))

    # Glowing neon cyan leading edge (+X side)
    edge = trimesh.creation.box(extents=[0.07, 1.30, 0.055])
    edge.apply_translation([0.11, 0.35, 0.0])
    parts.append(_colored_part(edge, (38, 238, 255)))

    # Tip bevel cone
    tip = trimesh.creation.cone(radius=0.13, height=0.28, sections=4)
    r_up = trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])
    r_45 = trimesh.transformations.rotation_matrix(math.pi / 4, [0, 1, 0])
    tip.apply_transform(r_45 @ r_up)
    tip.apply_scale([1.15, 1.0, 0.48])
    tip.apply_translation([0.02, 0.98, 0.0])
    parts.append(_colored_part(tip, (55, 245, 255)))

    # Octagonal cyber tsuba guard
    guard = trimesh.creation.cylinder(radius=0.28, height=0.10, sections=8)
    guard.apply_transform(r_up)
    guard.apply_scale([1.15, 1.0, 0.72])
    guard.apply_translation([0.0, -0.31, 0.0])
    parts.append(_colored_part(guard, (245, 182, 42)))

    # Power cell collar on front/back of blade base
    collar = trimesh.creation.box(extents=[0.28, 0.18, 0.16])
    collar.apply_translation([0.0, -0.20, 0.0])
    parts.append(_colored_part(collar, (235, 65, 85)))

    # Wrapped handle (tsuka)
    grip = trimesh.creation.cylinder(radius=0.085, height=0.52, sections=16)
    grip.apply_transform(r_up)
    grip.apply_scale([1.15, 1.0, 0.85])
    grip.apply_translation([0.0, -0.60, 0.0])
    parts.append(_colored_part(grip, (32, 36, 48)))

    for i, yy in enumerate((-0.44, -0.56, -0.68)):
        band = trimesh.creation.box(extents=[0.21, 0.05, 0.16])
        band.apply_translation([0.0, yy, 0.0])
        parts.append(_colored_part(band, (235, 65, 85) if i % 2 == 0 else (38, 238, 255)))

    # Pommel cap
    pommel = trimesh.creation.cylinder(radius=0.12, height=0.09, sections=8)
    pommel.apply_transform(r_up)
    pommel.apply_translation([0.0, -0.88, 0.0])
    parts.append(_colored_part(pommel, (245, 182, 42)))
    return parts


def _build_treasure_chest_parts() -> List[Tuple[trimesh.Trimesh, np.ndarray]]:
    parts = []
    # Wooden lower box
    base = trimesh.creation.box(extents=[0.96, 0.48, 0.66])
    base.apply_translation([0.0, -0.14, 0.0])
    parts.append(_colored_part(base, (138, 78, 36)))

    # Domed wooden lid (cylinder along X axis)
    lid = trimesh.creation.cylinder(radius=0.33, height=0.96, sections=24)
    r_x = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
    lid.apply_transform(r_x)
    lid.apply_translation([0.0, 0.10, 0.0])
    parts.append(_colored_part(lid, (156, 90, 42)))

    # Gold/Iron vertical straps at left/right/center
    for xx in (-0.36, 0.0, 0.36):
        strap_box = trimesh.creation.box(extents=[0.10, 0.52, 0.70])
        strap_box.apply_translation([xx, -0.13, 0.0])
        parts.append(_colored_part(strap_box, (232, 184, 52)))

        strap_arch = trimesh.creation.cylinder(radius=0.355, height=0.10, sections=24)
        strap_arch.apply_transform(r_x)
        strap_arch.apply_translation([xx, 0.10, 0.0])
        parts.append(_colored_part(strap_arch, (232, 184, 52)))

    # Horizontal rim band
    rim = trimesh.creation.box(extents=[1.00, 0.09, 0.70])
    rim.apply_translation([0.0, 0.09, 0.0])
    parts.append(_colored_part(rim, (72, 78, 90)))

    # Front brass padlock (+Z)
    lock_plate = trimesh.creation.box(extents=[0.22, 0.26, 0.10])
    lock_plate.apply_translation([0.0, 0.05, 0.35])
    parts.append(_colored_part(lock_plate, (248, 204, 64)))

    gem = trimesh.creation.icosphere(subdivisions=2, radius=0.065)
    gem.apply_translation([0.0, 0.06, 0.40])
    parts.append(_colored_part(gem, (42, 224, 155)))

    # Rear iron hinges (-Z)
    for xx in (-0.26, 0.26):
        hinge = trimesh.creation.box(extents=[0.12, 0.22, 0.09])
        hinge.apply_translation([xx, 0.08, -0.35])
        parts.append(_colored_part(hinge, (88, 94, 108)))

    # Side handles (+X / -X)
    for sx in (-1.0, 1.0):
        handle = trimesh.creation.box(extents=[0.09, 0.14, 0.26])
        handle.apply_translation([sx * 0.50, -0.10, 0.0])
        parts.append(_colored_part(handle, (232, 184, 52)))
    return parts


def _build_mecha_core_parts() -> List[Tuple[trimesh.Trimesh, np.ndarray]]:
    parts = []
    # Central armored chassis
    hull = trimesh.creation.icosphere(subdivisions=3, radius=0.40)
    hull.apply_scale([1.05, 0.92, 1.05])
    parts.append(_colored_part(hull, (58, 72, 98)))

    belt = trimesh.creation.cylinder(radius=0.44, height=0.14, sections=12)
    r_up = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])
    belt.apply_transform(r_up)
    parts.append(_colored_part(belt, (235, 148, 38)))

    # Front optic visor ring & glowing core (+Z)
    optic_ring = trimesh.creation.cylinder(radius=0.22, height=0.16, sections=24)
    optic_ring.apply_translation([0.0, 0.04, 0.36])
    parts.append(_colored_part(optic_ring, (220, 228, 240)))

    optic_eye = trimesh.creation.icosphere(subdivisions=2, radius=0.15)
    optic_eye.apply_translation([0.0, 0.04, 0.42])
    parts.append(_colored_part(optic_eye, (40, 232, 255)))

    # Twin side thruster pods (+X / -X)
    for sx in (-1.0, 1.0):
        arm = trimesh.creation.box(extents=[0.24, 0.14, 0.18])
        arm.apply_translation([sx * 0.44, 0.0, 0.0])
        parts.append(_colored_part(arm, (90, 102, 122)))

        pod = trimesh.creation.cylinder(radius=0.16, height=0.46, sections=16)
        pod.apply_transform(r_up)
        pod.apply_transform(trimesh.transformations.rotation_matrix(0.22, [1, 0, 0]))
        pod.apply_translation([sx * 0.56, -0.02, -0.02])
        parts.append(_colored_part(pod, (228, 234, 245)))

        nozzle = trimesh.creation.cone(radius=0.14, height=0.18, sections=16)
        nozzle.apply_transform(r_up)
        nozzle.apply_translation([sx * 0.56, -0.28, -0.04])
        parts.append(_colored_part(nozzle, (255, 112, 48)))

    # Dorsal stabilizer fins (+Y) & rear power pack (-Z)
    for sx in (-0.18, 0.18):
        fin = trimesh.creation.box(extents=[0.07, 0.34, 0.28])
        fin.apply_translation([sx, 0.40, -0.08])
        parts.append(_colored_part(fin, (235, 148, 38)))

    pack = trimesh.creation.box(extents=[0.42, 0.34, 0.20])
    pack.apply_translation([0.0, 0.02, -0.38])
    parts.append(_colored_part(pack, (42, 50, 68)))

    vent = trimesh.creation.box(extents=[0.26, 0.16, 0.08])
    vent.apply_translation([0.0, 0.02, -0.47])
    parts.append(_colored_part(vent, (255, 95, 58)))
    return parts


def render_orthographic_views(
    parts: List[Tuple[trimesh.Trimesh, np.ndarray]],
    img_size: int = 512,
    margin_ratio: float = 0.12,
) -> Dict[str, Image.Image]:
    """Software Z-buffer orthographic renderer producing 100% consistent 4-view RGBA sheets."""
    meshes = [p[0] for p in parts]
    colors = np.concatenate([p[1] for p in parts], axis=0)
    combined = trimesh.util.concatenate(meshes)

    verts = combined.vertices.copy()
    faces = combined.faces.copy()
    fnormals = combined.face_normals.copy()

    # Normalize into [-0.5, +0.5] preserving aspect ratio
    bmin, bmax = verts.min(axis=0), verts.max(axis=0)
    center = 0.5 * (bmin + bmax)
    max_span = float(max(np.max(bmax - bmin), 1e-5))
    verts = (verts - center) / max_span  # within [-0.5, 0.5]

    # Supersample 2x for crisp anti-aliased RGBA edges
    SS = img_size * 2
    scale_px = SS * (1.0 - 2.0 * margin_ratio)

    # Cameras: (u_axis_vec, v_axis_vec, depth_vec_towards_camera)
    # Matches roblox_pipeline.py & visual_hull.py:
    # front (+Z): u = +X, v = +Y, depth = +Z
    # back  (-Z): u = -X, v = +Y, depth = -Z
    # right (+X): u = -Z, v = +Y, depth = +X
    # left  (-X): u = +Z, v = +Y, depth = -X
    cameras = {
        "front": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
        "back":  (np.array([-1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, -1.0])),
        "right": (np.array([0.0, 0.0, -1.0]), np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0])),
        "left":  (np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0]), np.array([-1.0, 0.0, 0.0])),
    }

    out_imgs: Dict[str, Image.Image] = {}
    for vname, (u_ax, v_ax, d_ax) in cameras.items():
        u_proj = (verts @ u_ax) * scale_px + (SS * 0.5)
        v_proj = -(verts @ v_ax) * scale_px + (SS * 0.5)
        z_depth = verts @ d_ax

        # Backface cull + sort faces back-to-front (painter + z-test via sorted triangles)
        face_z = z_depth[faces].mean(axis=1)
        facing = (fnormals @ d_ax) >= -0.15
        valid_idx = np.where(facing)[0]
        order = valid_idx[np.argsort(face_z[valid_idx])]  # back-to-front

        # Studio 3-point lighting relative to viewing camera (even illumination for clean texture baking)
        key_dir = d_ax * 0.65 + u_ax * 0.35 + v_ax * 0.55
        key_dir /= np.linalg.norm(key_dir)
        fill_dir = d_ax * 0.55 - u_ax * 0.45 - v_ax * 0.20
        fill_dir /= np.linalg.norm(fill_dir)

        ndotl_key = np.clip(fnormals @ key_dir, 0.0, 1.0)
        ndotl_fill = np.clip(fnormals @ fill_dir, 0.0, 1.0)
        shade = 0.42 + 0.46 * ndotl_key + 0.18 * ndotl_fill  # [0.42, 1.06]

        shaded_colors = np.clip(colors.astype(np.float32) * shade[:, None], 0, 255).astype(np.uint8)

        canvas_rgb = np.zeros((SS, SS, 3), dtype=np.uint8)
        canvas_a = np.zeros((SS, SS), dtype=np.uint8)

        pts_2d = np.stack([u_proj, v_proj], axis=1)
        for fi in order:
            f = faces[fi]
            tri_pts = np.round(pts_2d[f]).astype(np.int32).reshape((-1, 1, 2))
            col = tuple(int(x) for x in shaded_colors[fi])
            cv2.fillConvexPoly(canvas_rgb, tri_pts, col, lineType=cv2.LINE_AA)
            cv2.fillConvexPoly(canvas_a, tri_pts, 255, lineType=cv2.LINE_AA)

        rgba_ss = np.dstack([canvas_rgb, canvas_a])
        pil_img = Image.fromarray(rgba_ss, mode="RGBA").resize(
            (img_size, img_size), Image.Resampling.LANCZOS
        )
        out_imgs[vname] = pil_img

    return out_imgs


def ensure_sample_sheets_generated(samples_root: Path) -> List[Dict[str, Any]]:
    """Generate all 4 sample 4-view turnaround image sets on disk if not yet present."""
    samples_root.mkdir(parents=True, exist_ok=True)
    builders = {
        "dragon_helm": _build_dragon_helm_parts,
        "cyber_katana": _build_cyber_katana_parts,
        "treasure_chest": _build_treasure_chest_parts,
        "mecha_core": _build_mecha_core_parts,
    }

    enriched: List[Dict[str, Any]] = []
    for item in SAMPLE_CATALOG:
        sid = item["id"]
        sdir = samples_root / sid
        sdir.mkdir(parents=True, exist_ok=True)
        expected = [sdir / f"{v}.png" for v in ("front", "left", "back", "right")]
        if not all(p.exists() for p in expected):
            views = render_orthographic_views(builders[sid](), img_size=512)
            for vname, pimg in views.items():
                pimg.save(sdir / f"{vname}.png", format="PNG")

        entry = dict(item)
        entry["views"] = {
            v: f"/samples/{sid}/{v}.png" for v in ("front", "left", "back", "right")
        }
        enriched.append(entry)

    return enriched
