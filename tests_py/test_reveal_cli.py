from __future__ import annotations

import importlib
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from backend.builds import BuildStore

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "targets/linux-sbc-hub75/runtime"


class RevealCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(RUNTIME))
        cls.main_module = importlib.import_module("scoreboard_device.__main__")

    def _staged_root(self, directory: Path) -> Path:
        project = json.loads((ROOT / "fixtures/project.json").read_text(encoding="utf-8"))
        store = BuildStore(directory / "builds")
        result = store.build(project)
        _, artifact_path = store.artifact(result["buildId"])
        extracted = directory / "extracted"
        with tarfile.open(artifact_path) as archive:
            archive.extractall(extracted, filter="data")
        return extracted

    def _run(self, root: Path, *args: str) -> int:
        argv = sys.argv
        sys.argv = ["scoreboard-device", "--root", str(root), *args]
        try:
            return self.main_module.main()
        finally:
            sys.argv = argv

    def test_arm_then_disarm_round_trips_through_the_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_root(Path(directory))
            self.assertEqual(self._run(root, "reveal", "arm"), 0)
            state = json.loads((root / "state/reveal.json").read_text())
            self.assertEqual(state["state"], "armed")

            self.assertEqual(self._run(root, "reveal", "disarm"), 0)
            state = json.loads((root / "state/reveal.json").read_text())
            self.assertEqual(state["state"], "disarmed")

    def test_illegal_transition_via_cli_fails_and_leaves_state_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_root(Path(directory))
            # disarm from the default "disarmed" state is not a legal transition.
            self.assertEqual(self._run(root, "reveal", "disarm"), 1)
            self.assertFalse((root / "state/reveal.json").exists())

    def test_rehearse_does_not_touch_reveal_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_root(Path(directory))
            project = json.loads((root / "config/project.json").read_text())
            project["reveal"] = {"lines": ["HI"], "lineDwellSec": 0.02, "fireworksDwellSec": 0.02}
            (root / "config/project.json").write_text(json.dumps(project))
            config = json.loads((root / "config/runtime-config.json").read_text())
            config["buttons"] = {"enabled": False}
            (root / "config/runtime-config.json").write_text(json.dumps(config))

            self.assertEqual(self._run(root, "rehearse", "--output", "simulator"), 0)
            self.assertFalse((root / "state/reveal.json").exists())


if __name__ == "__main__":
    unittest.main()
