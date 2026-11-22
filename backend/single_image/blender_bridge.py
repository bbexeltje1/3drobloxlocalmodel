from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poc_spec_blender.mesh_processing import build_mesh_inspection_script


class BlenderBridgeError(RuntimeError):
    pass


async def blender_mcp_status(client: Any) -> dict:
    """Use the one BlenderMCPClient owned by RoForge's main FastAPI application."""
    try:
        return await client.status()
    except Exception as exc:
        raise BlenderBridgeError(f"Blender MCP status check failed: {exc}") from exc


async def process_with_mcp(client: Any, mesh_path: Path, output_path: Path, timeout: int = 600) -> tuple[bytes, dict]:
    """Run the shared PoC mesh script through RoForge's existing MCP client instance."""
    if not mesh_path.is_file():
        raise BlenderBridgeError(f"Validated mesh is not present for Blender inspection: {mesh_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = build_mesh_inspection_script(mesh_path, output_path)
    try:
        # The MCP client uses its configured timeout; bound this handoff as well.
        import asyncio
        result_text = await asyncio.wait_for(
            client.execute(script, "Inspect the validated RoForge polygon mesh in a temporary collection, report triangles/bounds, and export GLB. Do not save or overwrite the open Blender scene."),
            timeout=timeout,
        )
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        raise BlenderBridgeError(f"Blender MCP mesh processing failed: {exc}") from exc
    if not output_path.is_file() or output_path.stat().st_size < 128:
        raise BlenderBridgeError("Blender MCP returned without producing an inspected GLB.")
    marker = "ROFORGE_MESH_INSPECTION="
    report_line = next((line.split(marker, 1)[1].strip() for line in result_text.splitlines() if marker in line), "{}")
    try:
        report = json.loads(report_line)
    except json.JSONDecodeError:
        report = {"message": result_text[-1000:]}
    return output_path.read_bytes(), {"content_type": "model/gltf-binary", "blender_report": report,
                                     "result": result_text}
