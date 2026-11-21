import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.download_budget3d_models import download_budget3d_models


class Budget3DDownloaderTests(unittest.TestCase):
    def test_downloads_public_files_without_auth_and_skips_existing_weights(self):
        calls = {"files": [], "snapshots": []}
        hub = types.ModuleType("huggingface_hub")

        def download(repo_id, filename, local_dir):
            calls["files"].append((repo_id, filename, local_dir))
            target = Path(local_dir) / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * 1_000_001)
            return str(target)

        def snapshot(repo_id, allow_patterns):
            calls["snapshots"].append((repo_id, allow_patterns))
            return "/cached/model"

        hub.hf_hub_download = download
        hub.snapshot_download = snapshot

        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"huggingface_hub": hub}):
            download_budget3d_models(Path(temp) / "Budget3D")
            self.assertEqual(len(calls["files"]), 2)
            self.assertEqual(len(calls["snapshots"]), 2)
            download_budget3d_models(Path(temp) / "Budget3D")
            # Checkpoint/config are retained locally; repeated setup only checks the public snapshots' cache.
            self.assertEqual(len(calls["files"]), 2)
            self.assertTrue(all("token" not in call for call in calls["files"]))


if __name__ == "__main__":
    unittest.main()
