from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.single_image.feynobg_local_dispatch import local_birefnet_tags, local_model_info


class LocalFeyNobgDispatchTests(unittest.TestCase):
    def test_identifies_expected_processor_from_local_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            (model_dir / "preprocessor_config.json").write_text(
                json.dumps({"image_processor_type": "BiRefNetImageProcessor"}), encoding="utf-8"
            )
            self.assertEqual(local_birefnet_tags(model_dir), ["nobg-birefnet"])

    def test_rejects_unrecognized_local_processor(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            (model_dir / "preprocessor_config.json").write_text(
                json.dumps({"image_processor_type": "OtherProcessor"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "does not identify the expected official"):
                local_birefnet_tags(model_dir)

    def test_model_info_is_overridden_only_for_the_local_model_path(self):
        remote_info = Mock(return_value=SimpleNamespace(tags=["remote-tag"]))
        auto_module = SimpleNamespace(model_info=remote_info)
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp).resolve()
            original = auto_module.model_info
            with local_model_info(auto_module, model_dir, ["nobg-birefnet"]):
                local_info = auto_module.model_info(str(model_dir))
                self.assertEqual(local_info.tags, ["nobg-birefnet"])
                with self.assertRaisesRegex(RuntimeError, "Refusing non-local"):
                    auto_module.model_info("feyninc/FeyNobg")
            self.assertIs(auto_module.model_info, original)
        remote_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
