from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_script import build_script  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
