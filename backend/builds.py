from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from backend.service import ROOT
from backend.validation import load_target_inputs, validate_target


BUILD_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{5,100}$")
ADAPTER_VERSION = "linux-sbc-hub75@1.0.0"
RUNTIME_VERSION = "0.6.3"
DRIVER_COMMIT = "e947417fff9042b3ea173542be09490acab069f7"
DRIVER_SOURCE_SHA256 = "a7862de04d63d501e734c1fe5f95ae3714903b40241d087680625b64147c11fa"


def _source_identity() -> dict[str, Any]:
    """Record a checkout identity without mislabeling dirty source as released."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3, check=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True, timeout=3, check=True
        ).stdout.strip())
        return {"commit": commit if len(commit) == 40 else "unknown", "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": "unknown", "dirty": True}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _private_logo_pack_files() -> dict[str, bytes]:
    directory = (ROOT / "frontend" / "public" / "private-assets" / "team-logos").resolve()
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest_payload = manifest_path.read_bytes()
    manifest = json.loads(manifest_payload)
    files = {"assets/team-logos/manifest.json": manifest_payload}
    for entry in manifest.get("assets", []):
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise ValueError("Logo manifest contains an invalid path")
        source = (directory / relative).resolve()
        if source.parent != directory or not source.is_file():
            raise ValueError(f"Logo asset is missing or unsafe: {relative}")
        payload = source.read_bytes()
        if _hash(payload) != entry.get("sha256"):
            raise ValueError(f"Logo asset checksum failed: {relative}")
        files[f"assets/team-logos/{relative}"] = payload
    return files


def _input_digest(
    project_payload: bytes,
    definition_payload: bytes,
    profile_payload: bytes,
    fonts_dir: Path,
    logo_pack_files: Mapping[str, bytes],
) -> str:
    inputs: dict[str, bytes] = {
        "config/project.json": project_payload,
        "definition/display-definition.json": definition_payload,
        "profile/device-profile.json": profile_payload,
    }
    roots = [
        ROOT / "schemas",
        ROOT / "shared_py",
        ROOT / "targets/linux-sbc-hub75/runtime/scoreboard_device",
        ROOT / "targets/linux-sbc-hub75/package",
        ROOT / "targets/linux-sbc-hub75/vendor",
    ]
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                inputs[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in sorted(fonts_dir.iterdir()):
        if path.is_file():
            inputs[f"definition/fonts/{path.name}"] = path.read_bytes()
    inputs.update(logo_pack_files)
    for path in (
        ROOT / "targets/linux-sbc-hub75/runtime-config.json",
        ROOT / "fixtures/demo-day.json",
        ROOT / "fixtures/demo-standings.json",
        ROOT / "fixtures/team-standings.json",
        ROOT / "fixtures/empty-day.json",
        ROOT / "fixtures/expected-render-frames.json",
        ROOT / "fixtures/arcade-replays.json",
        ROOT / "fixtures/nfl-demo.json",
        ROOT / "fixtures/nfl-frame-hashes.json",
        ROOT / "fixtures/nfl-logo-frame-hashes.json",
        ROOT / "fixtures/sports-frame-cases.json",
        ROOT / "fixtures/expected-playlist.json",
        ROOT / "fixtures/expected-mixed-playlist.json",
    ):
        inputs[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    digest = hashlib.sha256()
    for name, payload in sorted(inputs.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


def _validate_contract(filename: str, value: Any) -> None:
    schemas: dict[str, dict[str, Any]] = {}
    for path in (ROOT / "schemas").glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(schema, dict) and isinstance(schema.get("$id"), str):
            schemas[schema["$id"]] = schema
    schema_path = ROOT / "schemas" / filename
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry = Registry()
    for identifier, registered in schemas.items():
        registry = registry.with_resource(identifier, Resource.from_contents(registered))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda error: tuple(str(part) for part in error.absolute_path))
    if errors:
        evidence = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors[:10]
        )
        raise ValueError(f"{filename} contract failed: {evidence}")


def _copy(source: Path, destination: Path, mode: int | None = None) -> None:
    _write(destination, source.read_bytes(), mode if mode is not None else source.stat().st_mode & 0o777)


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def _tar_gz(root: Path) -> bytes:
    tar_payload = io.BytesIO()
    with tarfile.open(fileobj=tar_payload, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            name = path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = 0
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0, compresslevel=9) as compressed:
        compressed.write(tar_payload.getvalue())
    return output.getvalue()


class BuildError(RuntimeError):
    def __init__(self, stage: str, message: str, logs: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.stage = stage
        self.logs = logs


class BuildStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "builds"
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _log(logs: list[dict[str, str]], stage: str, status: str, message: str) -> None:
        logs.append({"atUtc": _utc_now(), "stage": stage, "status": status, "message": message})

    def build(
        self,
        project: Mapping[str, Any],
        *,
        acknowledged_warnings: Iterable[str] = (),
        bundle_dir: Path | None = None,
    ) -> dict[str, Any]:
        logs: list[dict[str, str]] = []
        self._log(logs, "validate", "running", "Validating project against the selected target profile")
        profile, definition, fonts_dir = load_target_inputs(project, bundle_dir=bundle_dir)
        validation = validate_target(
            project,
            profile,
            definition,
            fonts_dir=fonts_dir,
            acknowledged_warnings=acknowledged_warnings,
        )
        try:
            _validate_contract("validation-report.schema.json", validation)
        except ValueError as error:
            self._log(logs, "validate", "failed", str(error))
            raise BuildError("validate", str(error), logs) from error
        if validation["status"] != "valid":
            self._log(logs, "validate", "failed", "Blocking findings or unacknowledged warnings prevent build")
            raise BuildError("validate", "Project is not ready to build", logs)
        self._log(logs, "validate", "passed", "All seven target validation rules passed")

        project_payload = _json_bytes(project)
        definition_payload = _json_bytes(definition)
        profile_payload = _json_bytes(profile)
        logo_pack_files = _private_logo_pack_files()
        input_digest = _input_digest(
            project_payload,
            definition_payload,
            profile_payload,
            fonts_dir,
            logo_pack_files,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        build_id = f"{project['id']}-v{project['meta']['version']}-{input_digest[:10]}-{timestamp}".lower()
        build_dir = self.directory / build_id
        build_dir.mkdir(parents=True, exist_ok=False)
        artifact_filename = f"scoreboard-{project['id']}-v{project['meta']['version']}-linux-sbc-hub75.tar.gz"
        artifact_path = build_dir / artifact_filename

        try:
            with tempfile.TemporaryDirectory(prefix="assemble-", dir=build_dir) as temporary:
                stage = Path(temporary)
                self._log(logs, "resolve", "passed", f"Pinned input digest {input_digest}")
                _write(stage / "config" / "project.json", project_payload)
                _write(stage / "config" / "device-profile.json", profile_payload)
                _copy(ROOT / "targets/linux-sbc-hub75/runtime-config.json", stage / "config/runtime-config.json")
                _write(stage / "definition/display-definition.json", definition_payload)
                for source in sorted(fonts_dir.iterdir()):
                    if source.is_file():
                        _copy(source, stage / "definition/fonts" / source.name)
                for relative, payload in sorted(logo_pack_files.items()):
                    _write(stage / relative, payload)
                for name in (
                    "demo-day.json",
                    "demo-standings.json",
                    "team-standings.json",
                    "empty-day.json",
                    "expected-render-frames.json",
                    "arcade-replays.json",
                    "nfl-demo.json",
                    "nfl-frame-hashes.json",
                    "nfl-logo-frame-hashes.json",
                    "sports-frame-cases.json",
                    "expected-playlist.json",
                    "expected-mixed-playlist.json",
                ):
                    _copy(ROOT / "fixtures" / name, stage / "fixtures" / name)

                runtime_source = ROOT / "targets/linux-sbc-hub75/runtime/scoreboard_device"
                for source in sorted(runtime_source.glob("*.py")):
                    _copy(source, stage / "runtime/scoreboard_device" / source.name)
                for source in sorted((ROOT / "shared_py").glob("*.py")):
                    _copy(source, stage / "runtime/shared_py" / source.name)
                package_dir = ROOT / "targets/linux-sbc-hub75/package"
                _copy(package_dir / "requirements.lock.txt", stage / "runtime/requirements.lock.txt")
                _copy(package_dir / "install.sh", stage / "install.sh", 0o755)
                _copy(package_dir / "scoreboard.service", stage / "scoreboard.service")
                _copy(package_dir / "README-INSTALL.md", stage / "README-INSTALL.md")
                _copy(package_dir / "ASSEMBLY-GUIDE.md", stage / "ASSEMBLY-GUIDE.md")
                _copy(package_dir / "PILOT-BOM.md", stage / "PILOT-BOM.md")
                _copy(package_dir / "PILOT-ACCEPTANCE.md", stage / "PILOT-ACCEPTANCE.md")
                _copy(package_dir / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")
                vendor_dir = ROOT / "targets/linux-sbc-hub75/vendor"
                driver_archive = f"rpi-rgb-led-matrix-{DRIVER_COMMIT}-source.tar.gz"
                _copy(vendor_dir / driver_archive, stage / "vendor" / driver_archive)
                _copy(vendor_dir / "SOURCE-ARCHIVE.md", stage / "vendor" / "SOURCE-ARCHIVE.md")
                logo_count = max(0, len(logo_pack_files) - 1)
                self._log(
                    logs,
                    "assemble",
                    "passed",
                    f"Assembled runtime, exact definition, config, fonts, fixtures, installer, and {logo_count} team logo assets",
                )

                verification_dir = stage / "verification"
                environment = {
                    **os.environ,
                    "PYTHONPATH": str(stage / "runtime"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                command = [
                    sys.executable,
                    "-m",
                    "scoreboard_device",
                    "--root",
                    str(stage),
                    "verify",
                    "--output-dir",
                    str(verification_dir),
                ]
                completed = subprocess.run(
                    command,
                    cwd=stage,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if completed.returncode != 0:
                    self._log(logs, "verify", "failed", completed.stderr.strip() or completed.stdout.strip())
                    raise BuildError("verify", "Golden-frame verification failed", logs)
                verification = json.loads((verification_dir / "verification.json").read_text(encoding="utf-8"))
                _validate_contract("verification-report.schema.json", verification)
                self._log(logs, "verify", "passed", f"All {len(verification['frames'])} frames matched byte-for-byte")

                readiness = {
                    "schemaVersion": "1.0",
                    "status": "ready",
                    "projectId": project["id"],
                    "projectVersion": project["meta"]["version"],
                    "profile": profile,
                    "validation": validation,
                    "verification": verification,
                    "build": {
                        "id": build_id,
                        "adapterVersion": ADAPTER_VERSION,
                        "runtimeVersion": RUNTIME_VERSION,
                        "inputDigest": input_digest,
                        "artifactFilename": artifact_filename,
                    },
                    "installation": {
                        "panelCount": int(profile["logical"]["width"]) // 64,
                        "recommendedPower": "regulated 5 V, 8-10 A; panels powered directly",
                        "nextButton": "BCM25 to GND",
                        "holdButton": "BCM19 to GND",
                        "instructions": "README-INSTALL.md",
                        "assemblyGuide": "ASSEMBLY-GUIDE.md",
                        "billOfMaterials": "PILOT-BOM.md",
                        "acceptanceChecklist": "PILOT-ACCEPTANCE.md",
                    },
                    "knownLimitations": [
                        (
                            f"An optional {logo_count}-team logo pack is included; check its separate rights and notices before redistribution."
                            if logo_count
                            else "Official team logos are not included; add only assets you are authorized to use."
                        ),
                        "Hardware flicker, color order, power, thermals, and GPIO buttons remain pilot checks until exercised on the exact panel lot.",
                        "Commercial sale requires MLB data/mark review and GPL distribution review.",
                    ],
                }
                _validate_contract("readiness-report.schema.json", readiness)
                _write(stage / "readiness-report.json", _json_bytes(readiness))
                self._log(logs, "readiness", "passed", "System-issued ready status recorded with physical pilot limitations")

                self._log(logs, "checksum", "passed", "Prepared the complete artifact file set for SHA-256 recording")
                self._log(logs, "package", "passed", "Artifact payload finalized for deterministic compression")
                _write(stage / "build-log.json", _json_bytes({"schemaVersion": "1.0", "events": logs}))

                checksummed = _files(stage)
                manifest = {
                    "schemaVersion": "1.0",
                    "kind": "scoreboard-device-artifact",
                    "buildId": build_id,
                    "builtUtc": _utc_now(),
                    "project": {"id": project["id"], "version": project["meta"]["version"]},
                    "target": {"profileId": profile["id"], "targetClass": profile["targetClass"]},
                    "versions": {
                        "adapter": ADAPTER_VERSION,
                        "runtime": RUNTIME_VERSION,
                        "displayDefinition": project["displayDefinitionId"],
                        "projectSchema": project["schemaVersion"],
                        "driverCommit": DRIVER_COMMIT,
                        "driverSourceSha256": DRIVER_SOURCE_SHA256,
                    },
                    "inputDigest": input_digest,
                    "source": _source_identity(),
                    "requiredRuntime": {
                        "os": "Raspberry Pi OS Lite 64-bit or compatible Linux",
                        "python": ">=3.11",
                        "network": "Outbound HTTPS to statsapi.mlb.com",
                        "servicePort": 8123,
                    },
                    "files": {
                        name: {"sha256": _hash(payload), "bytes": len(payload)}
                        for name, payload in sorted(checksummed.items())
                    },
                }
                _validate_contract("artifact-manifest.schema.json", manifest)
                _write(stage / "manifest.json", _json_bytes(manifest))
                artifact = _tar_gz(stage)
                artifact_path.write_bytes(artifact)

            result = {
                "schemaVersion": "1.0",
                "buildId": build_id,
                "status": "ready",
                "artifactFilename": artifact_filename,
                "artifactSha256": _hash(artifact_path.read_bytes()),
                "artifactBytes": artifact_path.stat().st_size,
                "downloadUrl": f"/api/v1/builds/{build_id}/artifact",
                "manifest": manifest,
                "readiness": readiness,
                "logs": logs,
            }
            _write(build_dir / "build-result.json", _json_bytes(result))
            return result
        except BuildError:
            raise
        except Exception as error:
            self._log(logs, "package", "failed", str(error))
            raise BuildError("package", str(error), logs) from error

    def result(self, build_id: str) -> dict[str, Any]:
        if not BUILD_ID.fullmatch(build_id):
            raise FileNotFoundError(build_id)
        path = self.directory / build_id / "build-result.json"
        if not path.exists():
            raise FileNotFoundError(build_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def artifact(self, build_id: str) -> tuple[str, Path]:
        result = self.result(build_id)
        path = self.directory / build_id / result["artifactFilename"]
        if not path.is_file():
            raise FileNotFoundError(build_id)
        return result["artifactFilename"], path
