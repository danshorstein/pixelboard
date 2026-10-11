from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.service import ROOT
from shared_py.bdf import parse_bdf
from shared_py.renderer import resolve_settings


SEVERITIES = {"pass", "warning", "blocking"}


class TargetValidationError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finding(
    rule: str,
    severity: str,
    title: str,
    evidence: str,
    remediation: str | None = None,
) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise ValueError(f"Unsupported severity: {severity}")
    return {
        "rule": rule,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "remediation": remediation,
    }


def _scene_elements(definition: Mapping[str, Any], project: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    settings = resolve_settings(definition, project.get("designOverrides"))
    scenes = dict(definition.get("scenes", {}))
    preset = definition.get("presets", {}).get(settings["layoutPreset"])
    if isinstance(preset, Mapping):
        scenes.update(preset)
    return [
        element
        for scene in scenes.values()
        if isinstance(scene, Mapping)
        for element in scene.get("elements", [])
        if isinstance(element, Mapping)
    ]


def _font_names(
    definition: Mapping[str, Any],
    project: Mapping[str, Any],
    elements: Iterable[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], str]]:
    settings = resolve_settings(definition, project.get("designOverrides"))
    result: list[tuple[Mapping[str, Any], str]] = []
    for element in elements:
        raw = element.get("font")
        if not isinstance(raw, str):
            continue
        if raw.startswith("$fonts."):
            raw = settings["fonts"].get(raw.split(".", 1)[1], "")
        result.append((element, raw))
    return result


def _resolution(project: Mapping[str, Any], profile: Mapping[str, Any], definition: Mapping[str, Any]) -> dict[str, Any]:
    expected = definition.get("targetLogical", {})
    actual = profile.get("logical", {})
    if expected == actual:
        return _finding(
            "resolution-match",
            "pass",
            "Logical resolution matches",
            f"Definition and profile are both {actual.get('width')}x{actual.get('height')} pixels.",
        )
    return _finding(
        "resolution-match",
        "blocking",
        "Logical resolution is incompatible",
        f"The definition is {expected.get('width')}x{expected.get('height')}; {profile.get('id')} is {actual.get('width')}x{actual.get('height')}.",
        "Choose a 128x32 ticker profile or add a curated layout family for this logical size.",
    )


def _fonts(
    project: Mapping[str, Any],
    profile: Mapping[str, Any],
    definition: Mapping[str, Any],
    elements: list[Mapping[str, Any]],
    fonts_dir: Path,
) -> dict[str, Any]:
    failures: list[str] = []
    primary_small: list[str] = []
    checked: set[str] = set()
    for element, name in _font_names(definition, project, elements):
        path = fonts_dir / f"{name}.bdf"
        try:
            font = parse_bdf(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failures.append(name or "<empty>")
            continue
        checked.add(name)
        max_width = element.get("maxWidth")
        if isinstance(max_width, int) and max_width < min(font.width, font.height):
            failures.append(f"{name} in {max_width}px region")
        if element.get("bind") in {"away.score", "home.score", "scorelineDisplay"} and font.height < 5:
            primary_small.append(name)
    if failures:
        return _finding(
            "font-min-size",
            "blocking",
            "A required font cannot render safely",
            "Invalid or impossible font uses: " + ", ".join(sorted(set(failures))),
            "Restore the packaged BDF font or choose a larger declared text region.",
        )
    if primary_small:
        return _finding(
            "font-min-size",
            "warning",
            "Primary score font is unusually small",
            "Primary score uses: " + ", ".join(sorted(set(primary_small))),
            "Use a font at least 5 pixels high for room-distance readability.",
        )
    return _finding(
        "font-min-size",
        "pass",
        "Declared fonts fit the target",
        f"Validated {len(checked)} packaged BDF fonts and all bounded text regions.",
    )


def _effects(profile: Mapping[str, Any], elements: list[Mapping[str, Any]]) -> dict[str, Any]:
    used = {str(element.get("type")) for element in elements}
    supported = set(profile.get("capabilities", {}).get("supportedElements", []))
    unsupported = sorted(used - supported)
    if unsupported:
        return _finding(
            "effect-support",
            "blocking",
            "Definition uses unsupported primitives",
            "Unsupported: " + ", ".join(unsupported),
            "Remove those primitives or select a target adapter that implements them.",
        )
    fps = int(profile.get("capabilities", {}).get("maxAnimationFps", 0))
    severity = "pass" if fps >= 20 else "warning"
    return _finding(
        "effect-support",
        severity,
        "All display primitives are supported" if severity == "pass" else "Scrolling may appear uneven",
        f"All {len(used)} used primitives are supported; target maximum is {fps} fps.",
        None if severity == "pass" else "Use a target capable of at least 20 fps for marquee text.",
    )


def _assets(definition: Mapping[str, Any], elements: list[Mapping[str, Any]]) -> dict[str, Any]:
    invalid: list[str] = []
    bound = 0
    for element in elements:
        if element.get("type") != "sprite":
            continue
        if element.get("bind"):
            bound += 1
            continue
        asset = element.get("asset")
        if element.get("mode") == "rgb" and isinstance(asset, str) and not asset.lower().endswith(".png"):
            invalid.append(asset)
    if invalid:
        return _finding(
            "asset-format",
            "blocking",
            "An RGB sprite is not a PNG",
            "Invalid assets: " + ", ".join(invalid),
            "Convert target sprites to exact-size RGB/RGBA PNG files.",
        )
    return _finding(
        "asset-format",
        "pass",
        "Asset contract is device-safe",
        f"Validated static sprites; {bound} bound logo slot(s) retain the abbreviation fallback.",
    )


def _memory(profile: Mapping[str, Any], definition: Mapping[str, Any], fonts_dir: Path) -> dict[str, Any]:
    logical = profile.get("logical", definition.get("targetLogical", {}))
    frame_mb = int(logical.get("width", 0)) * int(logical.get("height", 0)) * 4 * 3 / 1_048_576
    font_mb = sum(path.stat().st_size for path in fonts_dir.glob("*.bdf")) / 1_048_576
    estimate = round(64 + frame_mb + font_mb, 1)
    budget = int(profile.get("capabilities", {}).get("memoryBudgetMb", 0))
    if estimate > budget:
        severity = "blocking"
    elif estimate > budget * 0.85:
        severity = "warning"
    else:
        severity = "pass"
    return _finding(
        "memory-estimate",
        severity,
        "Runtime memory is within budget" if severity == "pass" else "Runtime memory is near or over budget",
        f"Conservative estimate {estimate:.1f} MB; profile budget {budget} MB.",
        None if severity == "pass" else "Use a higher-memory SBC or reduce optional assets.",
    )


def _network(project: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    data = project.get("data", {})
    cadences = [data.get("refreshSecLive"), data.get("refreshSecPregame"), data.get("refreshSecIdle")]
    if any(isinstance(value, (int, float)) and value < 5 for value in cadences):
        return _finding(
            "network-assumption",
            "warning",
            "Provider refresh is too aggressive",
            f"Configured refresh values: {cadences} seconds.",
            "Keep every provider cadence at 5 seconds or slower.",
        )
    quiet = project.get("quietHours", {})
    is_bedroom_ticker = "ticker" in str(profile.get("id", ""))
    if is_bedroom_ticker and quiet.get("enabled") is not True:
        return _finding(
            "network-assumption",
            "warning",
            "Bedroom quiet hours are disabled",
            "The ticker will remain illuminated and continue normal fetching overnight.",
            "Enable quiet hours before installing in the display's room.",
        )
    return _finding(
        "network-assumption",
        "pass",
        "Network cadence and quiet hours are courteous",
        f"Minimum refresh is {min(int(value) for value in cadences)} seconds; quiet hours are configured.",
    )


def _configuration(project: Mapping[str, Any], definition: Mapping[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    if not project.get("favorites"):
        missing.append("favorites")
    rotation = project.get("rotation", {})
    for key in ("favoriteDwellSec", "otherDwellSec", "liveFirst", "favoritesFirst"):
        if key not in rotation:
            missing.append(f"rotation.{key}")
    data = project.get("data", {})
    if data.get("mode") not in {"live", "demo", "replay"}:
        missing.append("data.mode")
    expected_definition = f"{definition.get('id')}@{definition.get('version')}"
    if project.get("displayDefinitionId") != expected_definition:
        missing.append("displayDefinitionId")
    if missing:
        return _finding(
            "config-complete",
            "blocking",
            "Required device configuration is incomplete",
            "Missing or mismatched: " + ", ".join(missing),
            "Review the project settings and save before building.",
        )
    if data.get("mode") != "live":
        return _finding(
            "config-complete",
            "warning",
            "Device is configured for non-live data",
            f"The artifact will start in {data.get('mode')} mode.",
            "Select live mode for normal installation or acknowledge intentional demo use.",
        )
    return _finding(
        "config-complete",
        "pass",
        "Required device configuration is complete",
        f"Live mode with favorites {', '.join(project['favorites'])} and reviewed dwell settings.",
    )


RULES = {
    "resolution-match": _resolution,
    "font-min-size": _fonts,
    "effect-support": _effects,
    "asset-format": _assets,
    "memory-estimate": _memory,
    "network-assumption": _network,
    "config-complete": _configuration,
}


def validate_target(
    project: Mapping[str, Any],
    profile: Mapping[str, Any],
    definition: Mapping[str, Any],
    *,
    fonts_dir: Path,
    acknowledged_warnings: Iterable[str] = (),
    generated_utc: str | None = None,
) -> dict[str, Any]:
    elements = _scene_elements(definition, project)
    findings: list[dict[str, Any]] = []
    for rule in profile.get("validationRules", []):
        if rule == "resolution-match":
            finding = _resolution(project, profile, definition)
        elif rule == "font-min-size":
            finding = _fonts(project, profile, definition, elements, fonts_dir)
        elif rule == "effect-support":
            finding = _effects(profile, elements)
        elif rule == "asset-format":
            finding = _assets(definition, elements)
        elif rule == "memory-estimate":
            finding = _memory(profile, definition, fonts_dir)
        elif rule == "network-assumption":
            finding = _network(project, profile)
        elif rule == "config-complete":
            finding = _configuration(project, definition)
        else:
            finding = _finding(
                str(rule),
                "blocking",
                "Unknown validation rule",
                f"The adapter does not implement {rule}.",
                "Install a target adapter version that implements this rule.",
            )
        findings.append(finding)

    acknowledged = set(acknowledged_warnings)
    for finding in findings:
        finding["acknowledged"] = finding["severity"] == "warning" and finding["rule"] in acknowledged
    summary = {severity: sum(item["severity"] == severity for item in findings) for severity in SEVERITIES}
    unacknowledged = sum(
        item["severity"] == "warning" and not item["acknowledged"] for item in findings
    )
    if summary["blocking"]:
        status = "blocked"
    elif unacknowledged:
        status = "warnings"
    else:
        status = "valid"
    return {
        "schemaVersion": "1.0",
        "projectId": project.get("id"),
        "projectVersion": project.get("meta", {}).get("version"),
        "profileId": profile.get("id"),
        "targetClass": profile.get("targetClass"),
        "generatedUtc": generated_utc or _utc_now(),
        "status": status,
        "summary": {
            "pass": summary["pass"],
            "warning": summary["warning"],
            "blocking": summary["blocking"],
            "unacknowledgedWarnings": unacknowledged,
        },
        "findings": findings,
    }


def load_target_inputs(
    project: Mapping[str, Any],
    *,
    bundle_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Resolve the definition/profile/fonts for a project. A restored import's
    own bundle (see ProjectStore.bundle_dir) takes precedence over the
    repository's copy for that display-definition id — a restore must render
    exactly what was backed up, not whatever the repository currently ships."""
    if bundle_dir is not None:
        try:
            definition = json.loads((bundle_dir / "definition" / "display-definition.json").read_text(encoding="utf-8"))
            profile = json.loads((bundle_dir / "profile" / "device-profile.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TargetValidationError(f"Restored bundle is missing or invalid: {error}") from error
        return profile, definition, bundle_dir / "definition" / "fonts"
    definition_id = str(project.get("displayDefinitionId", "")).split("@", 1)[0]
    definition_dir = ROOT / "definition" / definition_id
    profile_path = ROOT / "targets" / "linux-sbc-hub75" / "profiles" / f"{project.get('profileId')}.json"
    try:
        definition = json.loads((definition_dir / "display-definition.json").read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TargetValidationError(f"Target input is missing or invalid: {error}") from error
    return profile, definition, definition_dir / "fonts"
