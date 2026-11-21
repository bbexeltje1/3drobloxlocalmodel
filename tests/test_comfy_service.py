import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.engines.comfy_service import ensure_comfyui_ready


class ComfyServiceTests(unittest.TestCase):
    def test_does_not_launch_when_comfyui_is_already_online(self):
        status = {"online": True, "url": "http://127.0.0.1:8188"}
        with patch("backend.engines.comfy_service._launch_comfyui") as launch:
            result = ensure_comfyui_ready(
                "http://127.0.0.1:8188", Path("."), status_check=lambda **_: status
            )
        self.assertIs(result, status)
        launch.assert_not_called()

    def test_starts_local_comfyui_and_waits_until_ready(self):
        statuses = iter([
            {"online": False},
            {"online": False},
            {"online": True, "device_name": "Test GPU"},
        ])
        check = lambda **_: next(statuses)
        with patch("backend.engines.comfy_service._launch_comfyui") as launch, patch(
            "backend.engines.comfy_service.time.sleep"
        ):
            result = ensure_comfyui_ready(
                "http://127.0.0.1:8188",
                Path(tempfile.gettempdir()),
                status_check=check,
                startup_timeout_sec=10,
                poll_interval_sec=0,
            )
        launch.assert_called_once()
        self.assertTrue(result["online"])
        self.assertEqual(result["device_name"], "Test GPU")

    def test_does_not_try_to_start_a_nonlocal_comfyui_endpoint(self):
        status = {"online": False, "url": "http://comfy.example:8188"}
        with patch("backend.engines.comfy_service._launch_comfyui") as launch:
            result = ensure_comfyui_ready(
                "http://comfy.example:8188", Path("."), status_check=lambda **_: status
            )
        self.assertIs(result, status)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
