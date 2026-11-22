from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "poc_spec_blender"))
from app import _build_mesh_inspection_script  # noqa: E402


class MeshInspectionScriptTests(unittest.TestCase):
    def test_mesh_inspection_script_compiles_and_is_temporary(self):
        script = _build_mesh_inspection_script(Path("candidate.glb"), Path("inspected.glb"))
        compile(script, "<blender-mesh-inspection>", "exec")
        self.assertIn("RoForge_SingleImage_Inspection_", script)
        self.assertIn("use_selection=True", script)
        self.assertIn("bpy.data.objects.remove", script)
        self.assertIn("bpy.data.collections.remove", script)
        self.assertNotIn("bpy.ops.wm.save_as_mainfile", script)


if __name__ == "__main__":
    unittest.main()
