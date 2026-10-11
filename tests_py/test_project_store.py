from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.project_store import ProjectConflictError, ProjectStore, ProjectValidationError, migrate_project


class ProjectStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_default_project_round_trip_bumps_server_version(self) -> None:
        project = self.store.default_project()
        saved = self.store.save(project)
        self.assertEqual(project["meta"]["version"] + 1, saved["meta"]["version"])
        self.assertEqual(saved, self.store.get(project["id"]))

    def test_schema_and_path_validation_fail_closed(self) -> None:
        with self.assertRaises(ProjectValidationError):
            self.store.get("../../escape")
        invalid = self.store.default_project()
        invalid["rotation"]["favoriteDwellSec"] = 0
        with self.assertRaises(ProjectValidationError):
            self.store.save(invalid)

    def test_export_and_import_use_safe_reproducible_contents(self) -> None:
        project = self.store.save(self.store.default_project())
        filename, payload = self.store.export_zip(project["id"])
        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIn("project.json", archive.namelist())
            self.assertIn("manifest.json", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertIn("definition/display-definition.json", manifest["files"])
            self.assertIn("profile/device-profile.json", manifest["files"])

        imported_store = ProjectStore(Path(self.temporary.name) / "imported")
        imported = imported_store.import_zip(payload)
        self.assertEqual(project["id"], imported["id"])

    def test_legacy_project_migrates_brightness_and_schema_version_without_dropping_fields(self) -> None:
        legacy = self.store.default_project()
        del legacy["brightness"]
        legacy["schemaVersion"] = "1.1"
        legacy["quietHours"]["start"] = "22:15"
        saved = self.store.save(legacy)
        self.assertEqual(saved["schemaVersion"], "1.2")
        self.assertEqual(saved["brightness"], {"normal": 35, "dim": 10})
        self.assertEqual(saved["quietHours"]["start"], "22:15")

    def test_migrate_project_is_pure_and_does_not_overwrite_present_brightness(self) -> None:
        project = self.store.default_project()
        project["brightness"] = {"normal": 80, "dim": 20}
        before = json.loads(json.dumps(project))
        migrated = migrate_project(project)
        self.assertEqual(project, before)
        self.assertEqual(migrated["brightness"], {"normal": 80, "dim": 20})

    def test_stale_expected_version_is_rejected_not_silently_overwritten(self) -> None:
        project = self.store.save(self.store.default_project())
        stale_version = project["meta"]["version"]
        self.store.save(project)
        conflicting = json.loads(json.dumps(project))
        conflicting["name"] = "Edited from a stale tab"
        with self.assertRaises(ProjectConflictError) as failure:
            self.store.save(conflicting, expected_version=stale_version)
        self.assertGreater(failure.exception.current["meta"]["version"], stale_version)
        reloaded = self.store.get(project["id"])
        self.assertNotEqual(reloaded["name"], "Edited from a stale tab")

    def test_import_restores_full_bundle_that_rendering_and_builds_can_resolve(self) -> None:
        project = self.store.save(self.store.default_project())
        _, payload = self.store.export_zip(project["id"])
        imported_store = ProjectStore(Path(self.temporary.name) / "imported")
        imported = imported_store.import_zip(payload)
        bundle = imported_store.bundle_dir(imported["id"])
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertTrue((bundle / "definition" / "display-definition.json").is_file())
        self.assertTrue((bundle / "profile" / "device-profile.json").is_file())
        self.assertTrue(any((bundle / "definition" / "fonts").iterdir()))

    def test_import_migrates_a_legacy_pre_brightness_backup_instead_of_rejecting_it(self) -> None:
        # Build an archive shaped like one exported before schemaVersion 1.2
        # existed: a legacy project.json (no brightness) whose manifest hash
        # was computed over those legacy bytes, exactly as a real old backup
        # would look.
        legacy_project = self.store.default_project()
        del legacy_project["brightness"]
        legacy_project["schemaVersion"] = "1.1"
        legacy_bytes = json.dumps(legacy_project, indent=2, sort_keys=True).encode() + b"\n"

        definition_bytes = (Path(__file__).resolve().parents[1] / "definition/mlb-classic/display-definition.json").read_bytes()
        profile_bytes = (
            Path(__file__).resolve().parents[1]
            / "targets/linux-sbc-hub75/profiles"
            / f"{legacy_project['profileId']}.json"
        ).read_bytes()
        files = {
            "project.json": legacy_bytes,
            "definition/display-definition.json": definition_bytes,
            "profile/device-profile.json": profile_bytes,
        }
        manifest = {
            "schemaVersion": "1.0",
            "kind": "scoreboard-project-export",
            "projectId": legacy_project["id"],
            "projectVersion": legacy_project["meta"]["version"],
            "exportedUtc": "2025-01-01T00:00:00Z",
            "files": {
                name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
                for name, content in files.items()
            },
        }
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest))

        imported_store = ProjectStore(Path(self.temporary.name) / "legacy-restore")
        restored = imported_store.import_zip(payload.getvalue())
        self.assertEqual(restored["schemaVersion"], "1.2")
        self.assertEqual(restored["brightness"], {"normal": 35, "dim": 10})

    def test_export_after_restore_reproduces_the_restored_bundle_not_the_repository(self) -> None:
        project = self.store.save(self.store.default_project())
        _, payload = self.store.export_zip(project["id"])
        imported_store = ProjectStore(Path(self.temporary.name) / "restored")
        imported = imported_store.import_zip(payload)

        bundle = imported_store.bundle_dir(imported["id"])
        assert bundle is not None
        original_bundle_definition = (bundle / "definition" / "display-definition.json").read_text()

        _, re_exported = imported_store.export_zip(imported["id"])
        with zipfile.ZipFile(io.BytesIO(re_exported)) as archive:
            re_exported_definition = archive.read("definition/display-definition.json").decode()
        self.assertEqual(re_exported_definition, original_bundle_definition)

    def test_import_rejects_a_tampered_file_even_if_project_json_is_untouched(self) -> None:
        project = self.store.save(self.store.default_project())
        _, payload = self.store.export_zip(project["id"])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            rebuilt = io.BytesIO()
            with zipfile.ZipFile(rebuilt, "w") as tampered:
                for name in names:
                    content = archive.read(name)
                    if name == "definition/display-definition.json":
                        content = content + b" "
                    tampered.writestr(name, content)
        imported_store = ProjectStore(Path(self.temporary.name) / "tampered")
        with self.assertRaises(ProjectValidationError):
            imported_store.import_zip(rebuilt.getvalue())
        # A rejected restore must not leave a half-written bundle behind.
        self.assertIsNone(imported_store.bundle_dir(project["id"]))

    def test_import_rejects_a_manifest_missing_a_required_file(self) -> None:
        project = self.store.save(self.store.default_project())
        _, payload = self.store.export_zip(project["id"])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            del manifest["files"]["profile/device-profile.json"]
            rebuilt = io.BytesIO()
            with zipfile.ZipFile(rebuilt, "w") as stripped:
                for name in archive.namelist():
                    if name in ("manifest.json", "profile/device-profile.json"):
                        continue
                    stripped.writestr(name, archive.read(name))
                stripped.writestr("manifest.json", json.dumps(manifest))
        imported_store = ProjectStore(Path(self.temporary.name) / "incomplete")
        with self.assertRaises(ProjectValidationError):
            imported_store.import_zip(rebuilt.getvalue())

    def test_import_rejects_traversal_member(self) -> None:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("../project.json", "{}")
        with self.assertRaises(ProjectValidationError):
            self.store.import_zip(payload.getvalue())


if __name__ == "__main__":
    unittest.main()
