import unittest

from backend.engines.comfy_pixal3d import build_pixal3d_mv_api_prompt


class Pixal3DPromptCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.prompt = build_pixal3d_mv_api_prompt({"front": "front.png"})

    def test_current_comfyui_background_removal_input_name(self):
        self.assertEqual(
            self.prompt["193"]["inputs"],
            {"bg_removal_name": "birefnet.safetensors"},
        )

    def test_current_comfyui_crop_to_mask_inputs(self):
        expected = {
            "images",
            "masks",
            "width",
            "height",
            "pad_factor",
            "grow_mask",
            "background",
        }
        for node_id in ("312", "349", "350", "352"):
            inputs = self.prompt[node_id]["inputs"]
            self.assertEqual(set(inputs), expected)
            self.assertEqual(inputs["pad_factor"], 1.1)
            self.assertEqual(inputs["grow_mask"], 0)
            self.assertEqual(inputs["background"], "#000000")

    def test_minimum_trellis_upsample_and_current_mesh_inputs(self):
        self.assertEqual(self.prompt["94"]["inputs"]["target_resolution"], 1024)
        self.assertEqual(self.prompt["241"]["inputs"]["qef"], False)
        self.assertEqual(self.prompt["241"]["inputs"]["fill"], 20.0)
        self.assertEqual(self.prompt["238"]["inputs"]["crease_angle"], 180.0)
        self.assertEqual(self.prompt["260"]["inputs"]["crease_angle"], 180.0)
        self.assertNotIn("max_angle", self.prompt["238"]["inputs"])


if __name__ == "__main__":
    unittest.main()
