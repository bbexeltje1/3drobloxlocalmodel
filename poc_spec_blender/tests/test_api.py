from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import httpx
    from httpx import ASGITransport
    import app as poc_app  # noqa: E402
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("Install poc_spec_blender/requirements.txt to run API route tests.") from exc

from spec import starter_spec  # noqa: E402


class OllamaDraftRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_reference_uploads_build_ollama_payload_and_return_spec(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": json.dumps(starter_spec())}}

        class FakeVLMClient:
            def __init__(self, **kwargs):
                self.options = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, json):
                captured["url"] = url
                captured["payload"] = json
                return FakeResponse()

        async with poc_app.app.router.lifespan_context(poc_app.app):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=poc_app.app),
                base_url="http://127.0.0.1",
            ) as client:
                with (
                    patch.object(poc_app, "VLM_URL", "http://127.0.0.1:11434/api/chat"),
                    patch.object(poc_app, "VLM_PROVIDER", "ollama"),
                    patch.object(poc_app, "VLM_MODEL", "qwen3.5:4b"),
                    patch.object(poc_app.httpx, "AsyncClient", FakeVLMClient),
                ):
                    response = await client.post(
                        "/api/draft-spec",
                        data={
                            "prompt": "Create a Gobble Rail",
                            "reference_labels": json.dumps(["Hero shot"]),
                        },
                        files=[("references", ("hero.png", b"hero image", "image/png"))],
                    )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["spec"]["asset_name"], starter_spec()["asset_name"])
        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "qwen3.5:4b")
        message = payload["messages"][0]
        self.assertIn("Image 1: Hero shot", message["content"])
        self.assertEqual(message["images"], [base64.b64encode(b"hero image").decode()])


if __name__ == "__main__":
    unittest.main()
