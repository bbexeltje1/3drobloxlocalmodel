from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_script import build_script  # noqa: E402
from mcp_client import BlenderMCPClient, BlenderMCPError  # noqa: E402
from spec import require_approval, starter_spec, validate_spec  # noqa: E402


class SpecTests(unittest.TestCase):
    def test_starter_spec_validates_and_flags_unknowns(self):
        spec, unknowns = validate_spec(starter_spec())
        self.assertEqual(spec["overall"]["length"], 10.0)
        self.assertGreaterEqual(len(unknowns), 3)
        self.assertEqual(next(p for p in spec["parts"] if p["id"] == "primary_feathers")["count"], 13)

    def test_build_requires_explicit_review(self):
        spec, _ = validate_spec(starter_spec())
        with self.assertRaisesRegex(ValueError, "Review the draft spec"):
            require_approval(spec)
        spec["approval"]["reviewed_by_user"] = True
        require_approval(spec)

    def test_rejects_invalid_color_and_duplicate_parts(self):
        spec = starter_spec()
        spec["palette"]["roast_skin"] = "orange"
        with self.assertRaisesRegex(ValueError, "six-digit hex"):
            validate_spec(spec)
        spec = starter_spec()
        spec["parts"].append(dict(spec["parts"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate part id"):
            validate_spec(spec)

    def test_generated_blender_python_compiles(self):
        spec, _ = validate_spec(starter_spec())
        source = build_script(spec, Path("C:/temp/Gobble_Rail.glb"))
        compile(source, "generated_blender_build.py", "exec")
        self.assertIn("export_format=\"GLB\"", source)
        self.assertIn("RoForge_GobbleRail_POC", source)


class MCPRequestLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_stdio_context_is_closed_in_the_request_task(self):
        client = BlenderMCPClient()
        opened_tasks = []
        closed_tasks = []

        class FakeStack:
            def __init__(self):
                self.owner = asyncio.current_task()
                opened_tasks.append(self.owner)

            async def aclose(self):
                closed_tasks.append(asyncio.current_task())
                if asyncio.current_task() is not self.owner:
                    raise RuntimeError("MCP context closed by a different task")

        class FakeSession:
            async def list_tools(self):
                return SimpleNamespace(tools=[
                    SimpleNamespace(name="get_addon_status"),
                    SimpleNamespace(name="execute_blender_code"),
                ])

            async def call_tool(self, name, arguments):
                message = "Blender add-on connected" if name == "get_addon_status" else "Build complete"
                return SimpleNamespace(content=[SimpleNamespace(text=message)], isError=False)

        async def fake_connect():
            if client._session is None:
                client._stack = FakeStack()
                client._session = FakeSession()
            return client._session

        client._connect = fake_connect
        first = await client.status()
        second = await client.status()
        built = await client.execute("pass", "test asset")

        self.assertTrue(first["connected"] and second["connected"])
        self.assertEqual(built, "Build complete")
        self.assertEqual(len(opened_tasks), 3)
        self.assertEqual(closed_tasks, opened_tasks)
        self.assertIsNone(client._session)
        self.assertIsNone(client._stack)

    async def test_failed_handshake_closes_request_scoped_session(self):
        client = BlenderMCPClient()
        owner_tasks = []
        closed_tasks = []

        class FakeStack:
            def __init__(self):
                self.owner = asyncio.current_task()
                owner_tasks.append(self.owner)

            async def aclose(self):
                closed_tasks.append(asyncio.current_task())
                if asyncio.current_task() is not self.owner:
                    raise RuntimeError("MCP context closed by a different task")

        class BrokenSession:
            async def list_tools(self):
                raise RuntimeError("simulated closed MCP stream")

        async def fake_connect():
            if client._session is None:
                client._stack = FakeStack()
                client._session = BrokenSession()
            return client._session

        client._connect = fake_connect
        with self.assertRaisesRegex(BlenderMCPError, "simulated closed MCP stream"):
            await client.status()

        self.assertEqual(closed_tasks, owner_tasks)
        self.assertIsNone(client._session)
        self.assertIsNone(client._stack)


if __name__ == "__main__":
    unittest.main()
