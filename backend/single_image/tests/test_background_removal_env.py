from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from backend.single_image.background_removal import _worker_environment
from backend.single_image.budget3d import _offline_environment


class WorkerEnvironmentTests(unittest.TestCase):
    def test_preserves_windows_username_for_torch_cache_initialization(self):
        with mock.patch.dict(os.environ, {"USERNAME": "local-user"}, clear=True):
            env = _worker_environment(Path(r"C:\Users\local-user\FeyNobg"))
        self.assertEqual(env["USERNAME"], "local-user")
        self.assertEqual(env["FEYNOBG_MODEL_DIR"], r"C:\Users\local-user\FeyNobg")
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")

    def test_budget3d_worker_preserves_windows_username_for_torch(self):
        with mock.patch.dict(os.environ, {"USERNAME": "local-user"}, clear=True):
            env = _offline_environment()
        self.assertEqual(env["USERNAME"], "local-user")
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")


if __name__ == "__main__":
    unittest.main()
