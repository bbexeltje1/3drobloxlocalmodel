import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from backend import main as app_module


class ComfyIdolApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output_dir = Path(self.temp.name) / "outputs"

    @staticmethod
    def _image_upload():
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (240, 40, 20)).save(buf, format="PNG")
        return {"front": ("object.png", buf.getvalue(), "image/png")}

    def _bundle_stub(self, **kwargs):
        return {
            "asset_name": "Test_Idol",
            "stats": {
                "hard_cap": 21000,
                "final_triangles": 12,
                "passes_preset_cap": True,
                "dimensions_studs": {"x": 1.0, "y": 1.0, "z": 1.0},
                "texture_size": 512,
                "is_watertight": True,
            },
            "lua_script": "-- test",
        }

    def test_comfy_idol_single_image_returns_mesh_bundle_plus_splat_artifacts(self):
        mesh_path = Path(self.temp.name) / "source.glb"
        trimesh.creation.box().export(mesh_path)
        result = {
            "ply_path": Path(self.temp.name) / "Test_Idol_gaussian.ply",
            "mesh_glb_path": mesh_path,
            "preview_path": Path(self.temp.name) / "Test_Idol_idol_preview.png",
            "turntable_path": Path(self.temp.name) / "Test_Idol_turntable.gif",
        }
        with (
            patch.object(app_module, "OUTPUTS_DIR", self.output_dir),
            patch.object(app_module, "_ensure_initial_demo", return_value={}),
            patch.object(app_module, "run_comfy_idol_single_image", return_value=result) as run_idol,
            patch.object(app_module, "export_complete_roblox_bundle", side_effect=self._bundle_stub),
            TestClient(app_module.app) as client,
        ):
            response = client.post(
                "/api/generate",
                data={"engine": "comfy_idol", "asset_name": "Test Idol", "idol_mode": "real"},
                files=self._image_upload(),
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIn("glb_url", data)
        self.assertTrue(data["splat_url"].endswith("_gaussian.ply"))
        self.assertTrue(data["idol_preview_url"].endswith("_idol_preview.png"))
        self.assertTrue(data["idol_turntable_url"].endswith("_turntable.gif"))
        self.assertIn("best-effort", data["engine_note"])
        run_idol.assert_called_once()
        self.assertEqual(run_idol.call_args.kwargs["mode"], "real")

    def test_comfy_idol_keeps_ply_when_mesh_conversion_fails(self):
        result = {
            "ply_path": Path(self.temp.name) / "Test_Idol_gaussian.ply",
            "mesh_glb_path": None,
            "preview_path": None,
            "turntable_path": None,
            "mesh_error": "GPU memory exhausted",
        }
        with (
            patch.object(app_module, "OUTPUTS_DIR", self.output_dir),
            patch.object(app_module, "_ensure_initial_demo", return_value={}),
            patch.object(app_module, "run_comfy_idol_single_image", return_value=result),
            patch.object(app_module, "export_complete_roblox_bundle") as export_bundle,
            TestClient(app_module.app) as client,
        ):
            response = client.post(
                "/api/generate",
                data={"engine": "comfy_idol"},
                files=self._image_upload(),
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["output_type"], "gaussian_splat")
        self.assertIn("GPU memory exhausted", data["engine_note"])
        export_bundle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
