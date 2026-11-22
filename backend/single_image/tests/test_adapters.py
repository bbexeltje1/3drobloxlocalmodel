from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh

from backend.single_image.preprocess import prepare_for_idol
from backend.single_image.gaussian_to_mesh import _mesh_from_file, GaussianConversionError, convert_budget3d_ply


class SingleImageAdapterTests(unittest.TestCase):
    def test_preprocess_keeps_full_frame_and_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            dest = root / "idol.png"
            rgba = Image.new("RGBA", (180, 90), (0, 0, 0, 0))
            # Thin detail at the extreme image edge verifies no crop/trim is applied.
            for x in range(3):
                for y in range(5, 85):
                    rgba.putpixel((x, y), (255, 20, 10, 255))
            rgba.save(source)
            details = prepare_for_idol(source, dest)
            self.assertTrue(dest.is_file())
            self.assertEqual(details["width"], 180)
            self.assertEqual(details["height"], 90)
            self.assertEqual(details["aspect_ratio"], 2.0)
            prepared = Image.open(dest)
            self.assertEqual(prepared.size, (180, 90))
            self.assertEqual(prepared.mode, "RGBA")
            pixels = np.array(prepared)
            self.assertTrue(np.any(pixels[:, :3, 0] > 200))
            self.assertTrue(np.all(pixels[5:85, :3, 3] == 255))
            self.assertEqual(pixels[45, 90, 3], 0)

    def test_converted_triangle_scene_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mesh.glb"
            trimesh.creation.box().export(path)
            mesh, report = _mesh_from_file(path)
            self.assertGreater(len(mesh.faces), 0)
            self.assertEqual(report["triangles"], len(mesh.faces))

    def test_point_cloud_is_not_misreported_as_mesh(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "points.ply"
            trimesh.points.PointCloud(np.random.default_rng(0).random((12, 3))).export(path)
            with self.assertRaisesRegex(GaussianConversionError, "no triangle faces"):
                _mesh_from_file(path)

    def test_unconfigured_gaussian_converter_fails_closed(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            ply = Path(tmp) / "splats.ply"
            ply.write_bytes(b"ply\n" + b" " * 200)
            with mock.patch.dict(os.environ, {"GAUSSIAN_MESH_CONVERTER": ""}):
                with self.assertRaisesRegex(GaussianConversionError, "not a mesh PLY"):
                    convert_budget3d_ply(ply, Path(tmp) / "converted.glb")


if __name__ == "__main__":
    unittest.main()
