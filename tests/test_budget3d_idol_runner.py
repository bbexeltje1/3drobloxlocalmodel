import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.engines.budget3d_idol import run_budget3d_idol_turbo


class Budget3DIdolRunnerTests(unittest.TestCase):
    def _make_install(self, home: Path) -> Path:
        python_path = (
            home / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else home / ".venv" / "bin" / "python"
        )
        paths = [
            python_path,
            home / "weights" / "budget3d_idol_turbo.safetensors",
            home / "scripts" / "sample.py",
            home / "third_party" / "idol-sdk" / "idol",
            home / "weights" / "dinov3" / "vith16plus_lvd1689m",
        ]
        for path in paths:
            if path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            else:
                path.mkdir(parents=True, exist_ok=True)
        return home

    def test_runs_the_single_image_turbo_cli_at_minimum_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self._make_install(Path(temp) / "Budget3D")
            image = Path(temp) / "front.png"
            image.write_bytes(b"image")
            output = Path(temp) / "out" / "result.ply"

            def fake_run(command, **kwargs):
                Path(command[command.index("--out") + 1]).write_bytes(b"ply")
                return subprocess.CompletedProcess(command, 0, "ok", "")

            with patch.dict(os.environ, {"BUDGET3D_HOME": str(home)}), patch(
                "backend.engines.budget3d_idol.subprocess.run", side_effect=fake_run
            ) as run:
                self.assertEqual(run_budget3d_idol_turbo(image, output), output)

            command = run.call_args.args[0]
            self.assertIn("--turbo", command)
            self.assertIn("--fast", command)
            self.assertEqual(command[command.index("--budget") + 1], "0.0625")
            self.assertEqual(command[command.index("--image") + 1], str(image.resolve()))
            self.assertEqual(command[command.index("--num_gaussians") + 1], "65536")

    def test_reports_missing_setup_instead_of_invoking_any_model(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"BUDGET3D_HOME": str(Path(temp) / "not-installed")}
        ):
            with self.assertRaisesRegex(RuntimeError, "not set up"):
                run_budget3d_idol_turbo(Path(temp) / "front.png", Path(temp) / "result.ply")


if __name__ == "__main__":
    unittest.main()
