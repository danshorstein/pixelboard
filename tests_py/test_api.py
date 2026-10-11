from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app


class ApiContractTests(unittest.TestCase):
    def test_health_and_demo_snapshot(self) -> None:
        with TestClient(app) as client:
            health = client.get("/api/health")
            self.assertEqual(200, health.status_code)
            self.assertEqual("ok", health.json()["status"])

            response = client.get("/api/v1/snapshot", params={"mode": "demo"})
            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual("demo", payload["mode"])
            self.assertEqual(11, len(payload["games"]))
            self.assertEqual(5, len(payload["standings"][0]["teams"]))
            self.assertEqual("fresh", payload["source"]["freshness"])

    def test_demo_websocket_pushes_the_same_contract(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/stream?mode=demo") as websocket:
                payload = websocket.receive_json()
                self.assertEqual("demo", payload["mode"])
                self.assertEqual(11, len(payload["games"]))

    def test_invalid_calendar_date_is_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/snapshot",
                params={"mode": "live", "date": "2026-99-99"},
            )
            self.assertEqual(400, response.status_code)

    def test_project_save_export_and_import_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(app) as client:
                app.state.project_store.directory = Path(directory)
                project_id = "pixelboard_m1_scoreboard"
                project = client.get(f"/api/v1/projects/{project_id}").json()
                project["name"] = "Pixelboard's Saved Scoreboard"
                saved = client.put(f"/api/v1/projects/{project_id}", json=project)
                self.assertEqual(200, saved.status_code)
                self.assertEqual(project["meta"]["version"] + 1, saved.json()["meta"]["version"])

                exported = client.get(f"/api/v1/projects/{project_id}/export")
                self.assertEqual(200, exported.status_code)
                self.assertEqual("application/zip", exported.headers["content-type"])

                imported = client.post(
                    "/api/v1/projects/import",
                    content=exported.content,
                    headers={"content-type": "application/zip"},
                )
                self.assertEqual(200, imported.status_code)
                self.assertEqual(project_id, imported.json()["id"])

    def test_reference_project_validates_for_the_supported_target(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects/pixelboard_m1_scoreboard/validate",
                json={"acknowledgedWarnings": []},
            )
            self.assertEqual(200, response.status_code, response.text)
            report = response.json()
            self.assertEqual("valid", report["status"])
            self.assertEqual("ticker-128x32-p4", report["profileId"])
            self.assertEqual(7, report["summary"]["pass"])

    def test_build_endpoint_returns_a_downloadable_ready_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(app) as client:
                # Build from the repository's reference project, not a saved
                # household project under SCOREBOARD_DATA_DIR. The frozen
                # frame hashes below describe the reference definition.
                app.state.project_store.directory = Path(directory) / "projects"
                app.state.project_store.bundles_directory = Path(directory) / "bundles"
                app.state.build_store.directory = Path(directory) / "builds"
                response = client.post(
                    "/api/v1/projects/pixelboard_m1_scoreboard/build",
                    json={"acknowledgedWarnings": []},
                )
                self.assertEqual(200, response.status_code, response.text)
                result = response.json()
                self.assertEqual("ready", result["status"])
                downloaded = client.get(result["downloadUrl"])
                self.assertEqual(200, downloaded.status_code)
                self.assertEqual(result["artifactBytes"], len(downloaded.content))
                self.assertEqual("application/gzip", downloaded.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
