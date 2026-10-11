from pathlib import Path
import importlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/linux-sbc-hub75/runtime"))
DeviceRuntime = importlib.import_module("scoreboard_device.runtime").DeviceRuntime

class DashboardUpdaterTests(unittest.TestCase):
    def test_update_runs_independently_and_targets_stable_link(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "scripts").mkdir()
            script = repo / "scripts/update-device.sh"
            script.write_text("#!/bin/bash\n")
            runtime = DeviceRuntime.__new__(DeviceRuntime)
            runtime.root = Path("/opt/pixelboard/releases/previous")
            with patch.object(runtime, "_find_git_repo", return_value=repo), patch(
                "scoreboard_device.runtime.subprocess.run") as run:
                self.assertTrue(runtime._web_apply_update()["ok"])
                args = run.call_args.args[0]
                self.assertEqual(args, ["systemd-run", "--unit=pixelboard-update",
                    "--collect", "--property=Type=exec", "bash", str(script),
                    "/opt/pixelboard"])
                self.assertTrue(run.call_args.kwargs["check"])
                self.assertEqual(run.call_args.kwargs["timeout"], 10)
                run.side_effect = subprocess.CalledProcessError(1, args)
                with self.assertRaises(subprocess.CalledProcessError):
                    runtime._web_apply_update()
