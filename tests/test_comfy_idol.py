import unittest

from backend.engines.comfy_idol import build_comfy_idol_api_prompt


class ComfyIdolPromptTests(unittest.TestCase):
    def test_single_image_idol_workflow_includes_splat_and_best_effort_mesh(self):
        prompt = build_comfy_idol_api_prompt(
            "input/front.png", seed=17, mode="real", mesh_resolution=128, asset_prefix="Test_Asset"
        )
        self.assertEqual(
            [node["class_type"] for node in prompt.values()].count("LoadImage"),
            1,
        )
        self.assertEqual(prompt["3"]["inputs"]["mode"], "real")
        self.assertEqual(prompt["9"]["inputs"]["steps"], 50)
        self.assertEqual(prompt["9"]["inputs"]["cfg"], 4.0)
        self.assertEqual(prompt["11"]["inputs"]["min_opacity"], 0.05)
        self.assertEqual(prompt["12"]["class_type"], "IdolCamera")
        self.assertEqual(prompt["13"]["inputs"]["camera_info"], ["12", 0])
        self.assertEqual(prompt["15"]["inputs"]["frames"], 24)
        self.assertEqual(prompt["18"]["inputs"]["mesh"], ["17", 0])
        self.assertEqual(prompt["19"]["inputs"]["resolution"], 128)
        self.assertEqual(prompt["20"]["inputs"]["mesh"], ["19", 0])
        self.assertEqual(prompt["20"]["inputs"]["filename_prefix"], "roforge_idol/Test_Asset_mesh")
        self.assertIn("LoadBackgroundRemovalModel", [n["class_type"] for n in prompt.values()])

    def test_transparent_input_uses_its_mask_without_birefnet(self):
        prompt = build_comfy_idol_api_prompt("cutout.png", has_alpha=True, mode="synthetic")
        types = [node["class_type"] for node in prompt.values()]
        self.assertIn("InvertMask", types)
        self.assertNotIn("LoadBackgroundRemovalModel", types)
        self.assertEqual(prompt["3"]["inputs"]["mask"], ["2", 0])
        self.assertEqual(prompt["3"]["inputs"]["mode"], "synthetic")

    def test_invalid_mode_and_mesh_resolution_are_rejected(self):
        with self.assertRaises(ValueError):
            build_comfy_idol_api_prompt("input.png", mode="portrait")
        with self.assertRaises(ValueError):
            build_comfy_idol_api_prompt("input.png", mesh_resolution=32)


if __name__ == "__main__":
    unittest.main()
