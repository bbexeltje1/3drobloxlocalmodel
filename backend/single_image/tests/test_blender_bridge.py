from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.single_image.blender_bridge import blender_mcp_status, process_with_mcp


class FakeMCPClient:
    def __init__(self, output: Path):
        self.output = output
        self.calls = []

    async def status(self):
        self.calls.append("status")
        return {"connected": True, "tools": ["get_addon_status", "execute_blender_code"]}

    async def execute(self, code: str, prompt: str):
        self.calls.append((code, prompt))
        self.output.write_bytes(b"glb" + b" " * 256)
        return 'ROFORGE_MESH_INSPECTION={"triangles":12,"dimensions":[1,2,3]}'


class BlenderBridgeTests(unittest.TestCase):
    def test_status_uses_app_owned_client(self):
        client = FakeMCPClient(Path("unused.glb"))
        status = asyncio.run(blender_mcp_status(client))
        self.assertTrue(status["connected"])
        self.assertEqual(client.calls, ["status"])

    def test_mesh_handoff_uses_same_client_and_parses_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.glb"
            output = root / "inspected.glb"
            source.write_bytes(b"source glb" + b" " * 200)
            client = FakeMCPClient(output)
            data, meta = asyncio.run(process_with_mcp(client, source, output))
            self.assertEqual(data, output.read_bytes())
            self.assertEqual(meta["blender_report"]["triangles"], 12)
            self.assertEqual(len(client.calls), 1)
            self.assertIn("RoForge_SingleImage_Inspection_", client.calls[0][0])
            self.assertIn("use_selection=True", client.calls[0][0])


if __name__ == "__main__":
    unittest.main()
