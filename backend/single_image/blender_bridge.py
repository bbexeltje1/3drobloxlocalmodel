from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx


class BlenderBridgeError(RuntimeError):
    pass


def existing_poc_status(timeout: int = 30) -> dict:
    base = os.getenv("BLENDER_POC_URL", "http://127.0.0.1:8765").rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base}/api/blender/status")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise BlenderBridgeError(f"Could not query existing Blender PoC at {base}: {exc}") from exc


def process_with_existing_poc(mesh_path: Path, timeout: int = 600) -> tuple[bytes, dict]:
    """Ask the existing local Blender PoC service to use its one MCP client instance."""
    base = os.getenv("BLENDER_POC_URL", "http://127.0.0.1:8765").rstrip("/")
    if not mesh_path.is_file():
        raise BlenderBridgeError(f"Validated mesh is not present for Blender inspection: {mesh_path}")
    try:
        with httpx.Client(timeout=timeout) as client:
            with mesh_path.open("rb") as f:
                response = client.post(f"{base}/api/mesh/process", files={"mesh_file": (mesh_path.name, f, "model/gltf-binary")})
            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise BlenderBridgeError(f"Existing Blender PoC rejected mesh processing (HTTP {response.status_code}): {detail}")
            encoded_report = response.headers.get("x-blender-report", "")
            try:
                report = json.loads(base64.urlsafe_b64decode(encoded_report.encode()).decode()) if encoded_report else {}
            except Exception:
                report = {"unparsed_report": encoded_report}
            metadata = {"content_type": response.headers.get("content-type", ""),
                        "blender_report": report}
            if "model/gltf-binary" not in metadata["content_type"] and "application/octet-stream" not in metadata["content_type"]:
                raise BlenderBridgeError("Blender PoC response did not contain a GLB mesh export.")
            return response.content, metadata
    except BlenderBridgeError:
        raise
    except httpx.HTTPError as exc:
        raise BlenderBridgeError(
            f"Could not reach the existing Blender PoC at {base}. Start it on the same PC; no second MCP connection was opened. Details: {exc}"
        ) from exc
