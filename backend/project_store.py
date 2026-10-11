from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from backend.service import ROOT

PROJECT_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ENTRIES = 50
MAX_IMPORT_UNCOMPRESSED = 20 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


class ProjectValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class ProjectConflictError(ValueError):
    """Raised when a save's expected base version no longer matches storage."""

    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__("Project was changed by another writer")
        self.current = current


_LEGACY_BRIGHTNESS_DEFAULT = {"normal": 35, "dim": 10}


def migrate_project(project: dict[str, Any]) -> dict[str, Any]:
    """Pure, versioned normalization. Fills in missing fields introduced by
    later schema versions without ever overwriting a present, valid value."""
    migrated = deepcopy(project)
    if "brightness" not in migrated or not isinstance(migrated.get("brightness"), Mapping):
        migrated["brightness"] = dict(_LEGACY_BRIGHTNESS_DEFAULT)
    else:
        merged = dict(_LEGACY_BRIGHTNESS_DEFAULT)
        merged.update(migrated["brightness"])
        migrated["brightness"] = merged
    if migrated.get("schemaVersion") in ("1.0", "1.1", None):
        migrated["schemaVersion"] = "1.2"
    return migrated


_EXPORT_MANIFEST_REQUIRED_FILES = (
    "project.json",
    "definition/display-definition.json",
    "profile/device-profile.json",
)


def _schema_validator(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / name).read_text())
    return Draft202012Validator(schema, format_checker=FormatChecker())


class ProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "projects"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.bundles_directory = data_dir / "bundles"
        self.bundles_directory.mkdir(parents=True, exist_ok=True)
        schema = json.loads((ROOT / "schemas" / "project.schema.json").read_text())
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self._definition_validator = _schema_validator("display-definition.schema.json")
        self._profile_validator = _schema_validator("device-profile.schema.json")

    def bundle_dir(self, project_id: str) -> Path | None:
        """A restored (imported) project's own definition/profile/fonts, kept
        separate from the trusted repository tree. Rendering and builds must
        prefer this over the repository's copy when it exists."""
        candidate = self.bundles_directory / project_id
        return candidate if (candidate / "manifest.json").is_file() else None

    def _path(self, project_id: str) -> Path:
        if not PROJECT_ID.fullmatch(project_id):
            raise ProjectValidationError(["Invalid project id"])
        return self.directory / f"{project_id}.json"

    def validate(self, project: Any, *, migrate: bool = True) -> dict[str, Any]:
        if not isinstance(project, Mapping):
            raise ProjectValidationError(["Project must be a JSON object"])
        candidate = migrate_project(dict(project)) if migrate else dict(project)
        errors = sorted(
            self.validator.iter_errors(candidate),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            formatted = [
                f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
                for error in errors[:20]
            ]
            raise ProjectValidationError(formatted)
        return deepcopy(candidate)

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                project = self.validate(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError, ProjectValidationError):
                continue
            projects.append({
                "id": project["id"],
                "name": project["name"],
                "version": project["meta"]["version"],
                "modified": project["meta"]["modified"],
            })
        if not projects:
            fixture = self.default_project()
            projects.append({
                "id": fixture["id"],
                "name": fixture["name"],
                "version": fixture["meta"]["version"],
                "modified": fixture["meta"]["modified"],
            })
        return projects

    def default_project(self) -> dict[str, Any]:
        return self.validate(json.loads((ROOT / "fixtures" / "project.json").read_text()))

    def get(self, project_id: str) -> dict[str, Any]:
        path = self._path(project_id)
        if not path.exists():
            fixture = self.default_project()
            if fixture["id"] == project_id:
                return fixture
            raise FileNotFoundError(project_id)
        return self.validate(json.loads(path.read_text()))

    def save(
        self,
        project: Any,
        *,
        bump_version: bool = True,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        validated = self.validate(project)
        path = self._path(validated["id"])
        existing: dict[str, Any] | None = None
        existing_version = 0
        if path.exists():
            try:
                existing = json.loads(path.read_text())
                existing_version = int(existing["meta"]["version"])
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                existing = None
                existing_version = 0
        if expected_version is not None and existing is not None and existing_version != expected_version:
            raise ProjectConflictError(self.validate(existing, migrate=True))
        if bump_version:
            validated["meta"]["version"] = max(
                existing_version,
                int(validated["meta"]["version"]),
            ) + 1
        validated["meta"]["modified"] = _utc_now()
        self.validate(validated)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(_json_bytes(validated))
        temporary.replace(path)
        return validated

    def export_zip(self, project_id: str) -> tuple[str, bytes]:
        project = self.get(project_id)
        bundle = self.bundle_dir(project_id)
        if bundle is not None:
            # A previously restored project must re-export exactly what was
            # restored, not silently swap back to whatever the repository's
            # definition currently is.
            definition_path = bundle / "definition" / "display-definition.json"
            profile_path = bundle / "profile" / "device-profile.json"
            fonts_dir = bundle / "definition" / "fonts"
        else:
            definition_id = str(project["displayDefinitionId"]).split("@", 1)[0]
            definition_path = ROOT / "definition" / definition_id / "display-definition.json"
            profile_path = ROOT / "targets" / "linux-sbc-hub75" / "profiles" / f"{project['profileId']}.json"
            fonts_dir = definition_path.parent / "fonts"
        files: dict[str, bytes] = {
            "project.json": _json_bytes(project),
            "definition/display-definition.json": definition_path.read_bytes(),
            "profile/device-profile.json": profile_path.read_bytes(),
        }
        for path in sorted(fonts_dir.iterdir()):
            if path.is_file():
                files[f"definition/fonts/{path.name}"] = path.read_bytes()
        manifest = {
            "schemaVersion": "1.0",
            "kind": "scoreboard-project-export",
            "projectId": project_id,
            "projectVersion": project["meta"]["version"],
            "exportedUtc": _utc_now(),
            "files": {
                name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
                for name, content in sorted(files.items())
            },
        }
        files["manifest.json"] = _json_bytes(manifest)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                archive.writestr(name, content)
        filename = f"scoreboard-project-{project_id}-v{project['meta']['version']}.zip"
        return filename, output.getvalue()

    def import_zip(self, payload: bytes) -> dict[str, Any]:
        if len(payload) > MAX_IMPORT_BYTES:
            raise ProjectValidationError(["Import exceeds 5 MB compressed limit"])
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except zipfile.BadZipFile as error:
            raise ProjectValidationError(["Import is not a valid ZIP archive"]) from error
        with archive:
            members = archive.infolist()
            if len(members) > MAX_IMPORT_ENTRIES:
                raise ProjectValidationError(["Import contains too many files"])
            total = sum(member.file_size for member in members)
            if total > MAX_IMPORT_UNCOMPRESSED:
                raise ProjectValidationError(["Import exceeds 20 MB expanded limit"])
            names: set[str] = set()
            for member in members:
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or member.is_dir():
                    if member.is_dir():
                        continue
                    raise ProjectValidationError(["Import contains an unsafe path"])
                unix_mode = member.external_attr >> 16
                if unix_mode & 0o170000 == 0o120000:
                    raise ProjectValidationError(["Import may not contain symbolic links"])
                names.add(member.filename)

            try:
                manifest_bytes = archive.read("manifest.json")
            except KeyError as error:
                raise ProjectValidationError(["Import is missing manifest.json"]) from error
            try:
                manifest = json.loads(manifest_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProjectValidationError(["manifest.json is invalid JSON"]) from error
            if (
                not isinstance(manifest, Mapping)
                or manifest.get("schemaVersion") != "1.0"
                or manifest.get("kind") != "scoreboard-project-export"
                or not isinstance(manifest.get("files"), Mapping)
            ):
                raise ProjectValidationError(["manifest.json is not a supported export manifest"])
            manifest_files = manifest["files"]
            for required in _EXPORT_MANIFEST_REQUIRED_FILES:
                if required not in manifest_files or required not in names:
                    raise ProjectValidationError([f"Import is missing required file: {required}"])

            contents: dict[str, bytes] = {}
            for name, recorded in manifest_files.items():
                if name not in names:
                    raise ProjectValidationError([f"Import is missing manifest-listed file: {name}"])
                if not isinstance(recorded, Mapping) or not isinstance(recorded.get("sha256"), str):
                    raise ProjectValidationError([f"manifest.json entry for {name} is malformed"])
                content = archive.read(name)
                if len(content) != recorded.get("bytes"):
                    raise ProjectValidationError([f"{name} size does not match the manifest"])
                if hashlib.sha256(content).hexdigest() != recorded["sha256"]:
                    raise ProjectValidationError([f"{name} checksum does not match the manifest — bundle is tampered or corrupt"])
                contents[name] = content

            try:
                project = json.loads(contents["project.json"])
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProjectValidationError(["project.json is invalid JSON"]) from error
            try:
                definition = json.loads(contents["definition/display-definition.json"])
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProjectValidationError(["definition/display-definition.json is invalid JSON"]) from error
            try:
                profile = json.loads(contents["profile/device-profile.json"])
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProjectValidationError(["profile/device-profile.json is invalid JSON"]) from error

            definition_errors = sorted(self._definition_validator.iter_errors(definition), key=str)
            if definition_errors:
                raise ProjectValidationError([f"definition: {error.message}" for error in definition_errors[:10]])
            profile_errors = sorted(self._profile_validator.iter_errors(profile), key=str)
            if profile_errors:
                raise ProjectValidationError([f"profile: {error.message}" for error in profile_errors[:10]])

            font_files = {
                name: content for name, content in contents.items()
                if name.startswith("definition/fonts/")
            }

        # Validate the project itself before writing anything to disk.
        validated_project = self.validate(project)

        # Restore atomically: build the new bundle in a staging directory,
        # then swap it in, so a failure partway through leaves the prior
        # valid bundle (and project) untouched.
        bundle_root = self.bundles_directory / validated_project["id"]
        staging = self.bundles_directory / f".{validated_project['id']}.staging"
        if staging.exists():
            _rmtree(staging)
        try:
            (staging / "definition" / "fonts").mkdir(parents=True, exist_ok=True)
            (staging / "profile").mkdir(parents=True, exist_ok=True)
            (staging / "definition" / "display-definition.json").write_bytes(
                contents["definition/display-definition.json"]
            )
            (staging / "profile" / "device-profile.json").write_bytes(contents["profile/device-profile.json"])
            for name, content in font_files.items():
                (staging / name).write_bytes(content)
            (staging / "manifest.json").write_bytes(manifest_bytes)

            saved = self.save(project)

            if bundle_root.exists():
                _rmtree(bundle_root)
            staging.replace(bundle_root)
        except Exception:
            if staging.exists():
                _rmtree(staging)
            raise
        return saved
