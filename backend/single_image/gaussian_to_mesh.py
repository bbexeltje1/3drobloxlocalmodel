from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import numpy as np
import trimesh


class GaussianConversionError(RuntimeError):
    pass


def conversion_status() -> dict:
    raw = os.getenv("GAUSSIAN_MESH_CONVERTER", "").strip()
    return {"configured": bool(raw), "command": raw or None,
            "note": "Adapter requires a converter that explicitly understands Budget3D Gaussian PLY; no built-in conversion is claimed."}


def _mesh_from_file(path: Path) -> tuple[trimesh.Trimesh, dict]:
    try:
        loaded = trimesh.load(str(path), force="scene", process=True)
    except Exception as exc:
        raise GaussianConversionError(f"Converter output could not be parsed as a triangle-mesh scene: {exc}") from exc
    try:
        # Scene.dump applies node transforms before flattening, so bounds/orientation stay correct.
        dumped = loaded.to_geometry() if isinstance(loaded, trimesh.Scene) else loaded
    except Exception as exc:
        raise GaussianConversionError(f"Could not flatten converted mesh scene with transforms: {exc}") from exc
    if not isinstance(dumped, trimesh.Trimesh) or not len(dumped.vertices) or not len(dumped.faces):
        raise GaussianConversionError("Conversion output contains no triangle faces; a point cloud/Gaussian splat is not a polygon mesh.")
    mesh = dumped
    if mesh.vertices.ndim != 2 or mesh.vertices.shape[1] != 3 or mesh.faces.ndim != 2 or mesh.faces.shape[1] != 3:
        raise GaussianConversionError("Conversion output is not a conventional triangular polygon mesh.")
    if not np.isfinite(mesh.vertices).all() or len(mesh.faces) < 4:
        raise GaussianConversionError("Converted mesh has non-finite vertices or too few faces to be a usable closed surface.")
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) < 4 or len(mesh.vertices) < 4 or not np.isfinite(mesh.bounds).all():
        raise GaussianConversionError("Converted mesh is degenerate after cleanup: insufficient faces/vertices or invalid bounds.")
    try:
        components = len(mesh.split(only_watertight=False))
    except Exception:
        # Connected-component analysis is diagnostic, not a reason to reject an otherwise
        # valid triangle mesh when an optional graph backend is absent.
        components = None
    report = {"vertices": int(len(mesh.vertices)), "triangles": int(len(mesh.faces)),
              "watertight": bool(mesh.is_watertight), "components": components,
              "bounds": mesh.bounds.tolist()}
    return mesh, report


def convert_budget3d_ply(gaussian_ply: Path, destination_glb: Path, timeout: int = 3600) -> tuple[trimesh.Trimesh, dict]:
    raw = os.getenv("GAUSSIAN_MESH_CONVERTER", "").strip()
    if not raw:
        raise GaussianConversionError(
            "No compatible Gaussian-to-mesh converter is configured. Budget3D's PLY is a Gaussian representation, "
            "not a mesh PLY. SuGaR or density extraction has not been verified against the local Budget3D output; "
            "configure GAUSSIAN_MESH_CONVERTER as a JSON command array with {input} and {output} placeholders "
            "only after validating that converter on this checkpoint's output."
        )
    if not gaussian_ply.is_file() or gaussian_ply.stat().st_size < 128:
        raise GaussianConversionError(f"Budget3D Gaussian PLY is missing or empty: {gaussian_ply}")
    try:
        command = json.loads(raw) if raw.startswith("[") else shlex.split(raw, posix=(os.name != "nt"))
    except Exception as exc:
        raise GaussianConversionError(f"GAUSSIAN_MESH_CONVERTER must be a command or JSON array: {exc}") from exc
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise GaussianConversionError("GAUSSIAN_MESH_CONVERTER must be a non-empty command array.")
    if not any("{input}" in x for x in command) or not any("{output}" in x for x in command):
        raise GaussianConversionError("Converter command must include {input} and {output} placeholders.")
    destination_glb.parent.mkdir(parents=True, exist_ok=True)
    try:
        args = [x.replace("{input}", str(gaussian_ply.resolve())).replace("{output}", str(destination_glb.resolve())) for x in command]
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GaussianConversionError(f"Gaussian-to-mesh conversion exceeded {timeout}s.") from exc
    except OSError as exc:
        raise GaussianConversionError(f"Could not launch configured converter: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "No converter output")[-3000:]
        raise GaussianConversionError(f"Gaussian-to-mesh converter failed (exit {result.returncode}): {detail}")
    if not destination_glb.is_file() or destination_glb.stat().st_size < 128:
        raise GaussianConversionError("Converter returned success but did not write the requested mesh GLB.")
    mesh, report = _mesh_from_file(destination_glb)
    report.update({"source_type": "Budget3D Gaussian PLY", "converted_path": str(destination_glb),
                   "converter": command[0]})
    return mesh, report
