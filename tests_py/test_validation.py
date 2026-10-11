from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from backend.project_store import ProjectStore
from backend.validation import load_target_inputs, validate_target


ROOT = Path(__file__).resolve().parents[1]


class TargetValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project = json.loads((ROOT / "fixtures/project.json").read_text(encoding="utf-8"))
        cls.project["data"]["provider"] = "mlb-stats-api"
        cls.project["data"]["mode"] = "live"
        cls.project["quietHours"].update({"enabled": True, "start": "21:30", "end": "07:00", "behavior": "dim"})

    def test_reference_profile_passes_every_rule(self) -> None:
        profile, definition, fonts_dir = load_target_inputs(self.project)
        report = validate_target(
            self.project,
            profile,
            definition,
            fonts_dir=fonts_dir,
            generated_utc="2026-07-16T20:00:00Z",
        )
        self.assertEqual("valid", report["status"])
        self.assertEqual(0, report["summary"]["blocking"])
        self.assertEqual(0, report["summary"]["warning"])
        self.assertEqual(7, report["summary"]["pass"])

    def test_incompatible_logical_size_is_blocking(self) -> None:
        project = deepcopy(self.project)
        project["profileId"] = "single-64x32-p4"
        profile, definition, fonts_dir = load_target_inputs(project)
        report = validate_target(project, profile, definition, fonts_dir=fonts_dir)
        self.assertEqual("blocked", report["status"])
        finding = next(item for item in report["findings"] if item["rule"] == "resolution-match")
        self.assertEqual("blocking", finding["severity"])
        self.assertIn("128x32", finding["remediation"])

    def test_warning_requires_explicit_acknowledgement(self) -> None:
        project = deepcopy(self.project)
        project["quietHours"]["enabled"] = False
        profile, definition, fonts_dir = load_target_inputs(project)
        report = validate_target(project, profile, definition, fonts_dir=fonts_dir)
        self.assertEqual("warnings", report["status"])
        acknowledged = validate_target(
            project,
            profile,
            definition,
            fonts_dir=fonts_dir,
            acknowledged_warnings=("network-assumption",),
        )
        self.assertEqual("valid", acknowledged["status"])

    def test_restored_bundle_takes_precedence_over_the_repository_definition(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            store = ProjectStore(Path(data_dir))
            project = store.save(store.default_project())
            _, payload = store.export_zip(project["id"])
            imported_store = ProjectStore(Path(data_dir) / "imported")
            imported = imported_store.import_zip(payload)
            bundle = imported_store.bundle_dir(imported["id"])

            _, from_repo, _ = load_target_inputs(imported)
            _, from_bundle, fonts_dir = load_target_inputs(imported, bundle_dir=bundle)
            self.assertEqual(from_repo, from_bundle)
            self.assertEqual(fonts_dir, bundle / "definition" / "fonts")

            # Mutate the bundle only — a restore must render exactly what was
            # backed up, not whatever the repository currently ships.
            definition_path = bundle / "definition" / "display-definition.json"
            mutated = json.loads(definition_path.read_text(encoding="utf-8"))
            mutated["version"] = "9.9"
            definition_path.write_text(json.dumps(mutated), encoding="utf-8")
            _, from_mutated_bundle, _ = load_target_inputs(imported, bundle_dir=bundle)
            self.assertEqual(from_mutated_bundle["version"], "9.9")
            self.assertNotEqual(from_mutated_bundle["version"], from_repo["version"])


if __name__ == "__main__":
    unittest.main()
