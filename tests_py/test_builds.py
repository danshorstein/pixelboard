from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from backend.builds import BuildStore


ROOT = Path(__file__).resolve().parents[1]


class BuildPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = json.loads((ROOT / "fixtures/project.json").read_text(encoding="utf-8"))

    def test_end_to_end_build_is_installable_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BuildStore(Path(directory))
            result = store.build(self.project)
            self.assertEqual("ready", result["status"])
            self.assertEqual("pass", result["readiness"]["verification"]["status"])
            filename, path = store.artifact(result["buildId"])
            self.assertEqual(result["artifactFilename"], filename)
            self.assertEqual(result["artifactSha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            with tarfile.open(fileobj=io.BytesIO(path.read_bytes()), mode="r:gz") as archive:
                names = set(archive.getnames())
                required = {
                    "manifest.json",
                    "readiness-report.json",
                    "README-INSTALL.md",
                    "ASSEMBLY-GUIDE.md",
                    "PILOT-BOM.md",
                    "PILOT-ACCEPTANCE.md",
                    "install.sh",
                    "scoreboard.service",
                    "runtime/scoreboard_device/runtime.py",
                    "runtime/shared_py/renderer.py",
                    "config/project.json",
                    "definition/display-definition.json",
                    "verification/verification.json",
                    "vendor/SOURCE-ARCHIVE.md",
                    "vendor/rpi-rgb-led-matrix-e947417fff9042b3ea173542be09490acab069f7-source.tar.gz",
                }
                self.assertTrue(required <= names)
                self.assertFalse(any(name.startswith("assets/team-logos/") for name in names))
                manifest = json.load(archive.extractfile("manifest.json"))
                self.assertEqual(result["buildId"], manifest["buildId"])
                install = archive.getmember("install.sh")
                self.assertTrue(install.mode & 0o100)
                install_text = archive.extractfile("install.sh").read().decode()
                self.assertNotIn("git clone", install_text)
                self.assertNotIn("git fetch", install_text)
                self.assertNotIn("git checkout", install_text)
                self.assertIn(manifest["versions"]["driverSourceSha256"], install_text)
                self.assertIn("--no-build-isolation", install_text)
                self.assertIn("--no-deps", install_text)
                # A reinstall over a running service must stage into a fresh
                # release directory, verify it before going live, explicitly
                # restart (not just enable --now, a no-op if already active),
                # and roll back the symlink on a failed health check.
                self.assertIn("RELEASE_DIR", install_text)
                self.assertIn("systemctl restart scoreboard.service", install_text)
                self.assertIn("rollback", install_text)
                self.assertIn("SERVICE_WAS_ACTIVE", install_text)
                driver_source = archive.extractfile(
                    "vendor/rpi-rgb-led-matrix-e947417fff9042b3ea173542be09490acab069f7-source.tar.gz"
                ).read()
                self.assertEqual(
                    manifest["versions"]["driverSourceSha256"],
                    hashlib.sha256(driver_source).hexdigest(),
                )
                for name, evidence in manifest["files"].items():
                    payload = archive.extractfile(name).read()
                    self.assertEqual(evidence["bytes"], len(payload), name)
                    self.assertEqual(evidence["sha256"], hashlib.sha256(payload).hexdigest(), name)

    def test_artifact_bytes_are_reproducible_for_the_same_staged_inputs(self) -> None:
        # The build timestamp lives in manifest metadata, so complete artifacts
        # are traceable rather than byte-identical. The pinned input digest is
        # stable and all runtime payloads are checksummed.
        with tempfile.TemporaryDirectory() as directory:
            store = BuildStore(Path(directory))
            first = store.build(self.project)
            second = store.build(self.project)
            self.assertEqual(first["manifest"]["inputDigest"], second["manifest"]["inputDigest"])
            self.assertEqual(first["manifest"]["versions"], second["manifest"]["versions"])


if __name__ == "__main__":
    unittest.main()
