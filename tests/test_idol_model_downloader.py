import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.download_models_6gb import download_comfyui_idol


class ComfyIdolDownloaderTests(unittest.TestCase):
    def test_downloads_public_idol_files_directly_and_skips_existing_files(self):
        calls = []
        hub = types.ModuleType("huggingface_hub")

        def download(repo_id, filename, local_dir):
            calls.append((repo_id, filename, local_dir))
            target = Path(local_dir) / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * 1_000_001)
            return str(target)

        hub.hf_hub_download = download
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"huggingface_hub": hub}):
            comfy_dir = Path(temp) / "ComfyUI"
            models_dir = comfy_dir / "models"
            existing = models_dir / "vae" / "flux2-vae.safetensors"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"x" * 1_000_001)

            download_comfyui_idol(comfy_dir)

            self.assertEqual(len(calls), 4)
            self.assertTrue(all(len(call) == 3 for call in calls))
            self.assertIn(("nynxz/Idol", "diffusion_models/idol_fp16.safetensors", str(models_dir)), calls)
            self.assertIn(("nynxz/Idol", "vae/idol_decoder_fp16.safetensors", str(models_dir)), calls)
            self.assertTrue((models_dir / "clip_vision" / "dino_v3_vit_h.safetensors").is_file())
            self.assertTrue((models_dir / "background_removal" / "birefnet.safetensors").is_file())


if __name__ == "__main__":
    unittest.main()
