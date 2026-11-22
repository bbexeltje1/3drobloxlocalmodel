"""Validation and starter design data for the isolated Blender MCP proof of concept."""
from __future__ import annotations

import copy
import re
from typing import Any

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

STARTER_SPEC: dict[str, Any] = {
    "asset_name": "Gobble_Rail_POC",
    "unit_mode": "normalized",
    "overall": {
        "length": 10.0,
        "height": 4.8,
        "width": 2.6,
        "source_note": "Reference spec gives a 10:4.8:2.6 proportion; total Roblox stud length is not specified.",
    },
    "palette": {
        "roast_skin": "#C86218",
        "feather_tips": "#FFD54F",
        "cranberry_gel": "#A0002D",
        "corn_kernels": "#ECC22B",
        "pie_filling": "#E07A1E",
        "brass_trim": "#C9A84C",
        "bone": "#F4E9D5",
        "dark_underbody": "#67351E",
    },
    "parts": [
        {"id": "primary_feathers", "label": "Primary feathers", "count": 13, "color": "feather_tips", "kind": "feather_fan", "exact": True},
        {"id": "turkey_receiver", "label": "Roast turkey receiver", "count": 1, "color": "roast_skin", "kind": "receiver", "exact": False},
        {"id": "corn_cobs", "label": "Corn rail cobs", "count": 2, "color": "corn_kernels", "kind": "corn_rail", "exact": False},
        {"id": "kernel_rows_per_cob", "label": "Kernel rows per cob", "count": 10, "color": "corn_kernels", "kind": "kernel_rows", "exact": False, "range": [10, 12], "provisional": True},
        {"id": "pie_coil_rings", "label": "Pie coil rings", "count": 2, "color": "pie_filling", "kind": "coil_ring", "exact": True},
        {"id": "cranberry_can_ribs", "label": "Cranberry magazine ribs", "count": 8, "color": "cranberry_gel", "kind": "can_ribs", "exact": True},
        {"id": "wishbone_muzzle", "label": "Wishbone muzzle", "count": 1, "color": "bone", "kind": "wishbone", "exact": False},
        {"id": "trigger", "label": "Trigger", "count": 1, "color": "brass_trim", "kind": "moving_trigger", "exact": False},
        {"id": "magazine", "label": "Cranberry magazine", "count": 1, "color": "cranberry_gel", "kind": "moving_magazine", "exact": False},
        {"id": "wattle", "label": "Wattle", "count": 1, "color": "cranberry_gel", "kind": "moving_wattle", "exact": False},
    ],
    "motions": [
        {"part_id": "trigger", "type": "rotation", "angle_degrees": 15, "axis": "Z", "timing": "on fire", "pivot": None, "provisional": True},
        {"part_id": "magazine", "type": "translation", "angle_degrees": 15, "axis": "down-and-forward", "pivot": None, "provisional": True},
        {"part_id": "wattle", "type": "pendulum_swing", "angle_degrees": None, "axis": "Z", "pivot": None, "provisional": True},
    ],
    "unknowns": [
        "Target overall length in Roblox studs is not given; current dimensions are normalized proportions only.",
        "The screenshots do not specify exact pivot coordinates or motion direction in Blender axes.",
        "Kernel rows are specified as 10–12; the starter uses 10 pending approval.",
        "Detailed part widths/depths and the precise overlap/placement are draft interpretations of the reference images.",
    ],
    "approval": {"reviewed_by_user": False},
}


def starter_spec() -> dict[str, Any]:
    return copy.deepcopy(STARTER_SPEC)


def validate_spec(data: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(data, dict):
        raise ValueError("Spec must be a JSON object.")
    spec = copy.deepcopy(data)
    name = spec.get("asset_name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("asset_name must be a non-empty string.")
    if len(name) > 64:
        raise ValueError("asset_name must be 64 characters or fewer.")
    spec["asset_name"] = name.strip()

    overall = spec.get("overall")
    if not isinstance(overall, dict):
        raise ValueError("overall must contain length, height, and width.")
    for field in ("length", "height", "width"):
        value = overall.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not (0 < float(value) <= 10000):
            raise ValueError(f"overall.{field} must be a positive number no greater than 10000.")

    palette = spec.get("palette")
    if not isinstance(palette, dict) or not palette:
        raise ValueError("palette must be a non-empty map of material names to #RRGGBB values.")
    for key, value in palette.items():
        if not isinstance(key, str) or not isinstance(value, str) or not HEX_RE.fullmatch(value):
            raise ValueError(f"palette entry {key!r} must use a six-digit hex color such as #C86218.")

    parts = spec.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("parts must be a non-empty array.")
    ids: set[str] = set()
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f"parts[{i}] must be an object.")
        part_id = part.get("id")
        if not isinstance(part_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", part_id):
            raise ValueError(f"parts[{i}].id must be a lowercase identifier using letters, digits, and underscores.")
        if part_id in ids:
            raise ValueError(f"Duplicate part id: {part_id}.")
        ids.add(part_id)
        count = part.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= 500):
            raise ValueError(f"parts[{i}].count must be an integer from 1 to 500.")
        color = part.get("color")
        if color not in palette:
            raise ValueError(f"parts[{i}].color must reference a key in palette.")
        if not isinstance(part.get("kind"), str):
            raise ValueError(f"parts[{i}].kind must be a string.")

    motions = spec.get("motions", [])
    if not isinstance(motions, list):
        raise ValueError("motions must be an array.")
    for i, motion in enumerate(motions):
        if not isinstance(motion, dict) or motion.get("part_id") not in ids:
            raise ValueError(f"motions[{i}] must reference a part id in parts.")

    unknowns = spec.get("unknowns", [])
    if not isinstance(unknowns, list) or any(not isinstance(x, str) for x in unknowns):
        raise ValueError("unknowns must be an array of strings.")
    return spec, list(unknowns)


def require_approval(spec: dict[str, Any]) -> None:
    approval = spec.get("approval", {})
    if not isinstance(approval, dict) or approval.get("reviewed_by_user") is not True:
        raise ValueError("Review the draft spec and check the approval box before sending any build command to Blender.")
