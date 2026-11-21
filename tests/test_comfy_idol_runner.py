import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.engines.comfy_idol import REQUIRED_NODE_TYPES, run_comfy_idol_single_image


class _Response:
    def __init__(self, payload=None, content=b"ok", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.is_error = status_code >= 400
        self.text = "test response"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.is_error:
            raise RuntimeError("unexpected status")


class _FakeClient:
    def __init__(self, **kwargs):
        self.prompt = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, params=None):
        if url.endswith("/system_stats"):
            return _Response({"devices": []})
        if url.endswith("/object_info"):
            return _Response({node: {} for node in REQUIRED_NODE_TYPES})
        if "/history/" in url:
            return _Response({"test-prompt": {
                "outputs": {
                    "18": {"3d": [{"filename": "asset.ply", "subfolder": "", "type": "output"}]},
                    "20": {"3d": [{"filename": "mesh.glb", "subfolder": "", "type": "output"}]},
                    "14": {"images": [{"filename": "preview.png", "subfolder": "", "type": "output"}]},
                    "16": {"images": [{"filename": "turntable_00001_.png", "subfolder": "", "type": "output"}]},
                },
                "status": {"completed": True, "messages": []},
            }})
        if url.endswith("/view"):
            filename = (params or {}).get("filename", "")
            if filename.endswith(".png"):
                stream = io.BytesIO()
                Image.new("RGB", (16, 16), (50, 100, 150)).save(stream, format="PNG")
                return _Response(content=stream.getvalue())
            return _Response(content=b"fake 3d artifact")
        raise AssertionError(f"Unexpected GET: {url}")

    def post(self, url, **kwargs):
        if url.endswith("/upload/image"):
            return _Response({"name": "uploaded.png"})
        if url.endswith("/prompt"):
            self.prompt = kwargs["json"]["prompt"]
            return _Response({"prompt_id": "test-prompt"})
        raise AssertionError(f"Unexpected POST: {url}")


class ComfyIdolRunnerTests(unittest.TestCase):
    def test_collects_ply_mesh_preview_and_turntable_without_external_services(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_path = root / "object.png"
            Image.new("RGB", (32, 32), (180, 30, 20)).save(image_path)
            output_dir = root / "output"
            with patch("backend.engines.comfy_idol.httpx.Client", _FakeClient):
                result = run_comfy_idol_single_image(
                    image_path,
                    output_dir=output_dir,
                    asset_prefix="Test",
                    comfy_url="http://comfy.test:8188",
                    mode="real",
                    timeout_sec=5,
                )

            self.assertTrue(result["ply_path"].is_file())
            self.assertTrue(result["mesh_glb_path"].is_file())
            self.assertTrue(result["preview_path"].is_file())
            self.assertTrue(result["turntable_path"].is_file())
            self.assertEqual(result["turntable_path"].suffix, ".gif")
            self.assertFalse(result.get("mesh_error"))


if __name__ == "__main__":
    unittest.main()
