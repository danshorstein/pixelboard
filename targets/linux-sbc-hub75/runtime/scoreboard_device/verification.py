from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from shared_py.png import encode_rgba_png
from shared_py.bdf import parse_bdf
from shared_py.renderer import render_scene
from shared_py.arcade import create_game, press_game, start_game, step_game, steer_snake, swing
from shared_py.arcade_frame import arcade_frame
from shared_py.nfl_frame import nfl_frame


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _paths(root: Path) -> tuple[Path, Path, Path]:
    artifact_definition = root / "definition" / "display-definition.json"
    if artifact_definition.exists():
        return artifact_definition, root / "definition" / "fonts", root / "config" / "project.json"
    if (root / "config" / "project.json").exists():
        raise FileNotFoundError(
            "packaged runtime is missing definition/display-definition.json; "
            "repository definition directories must be flattened during staging"
        )
    return (
        root / "definition" / "mlb-classic" / "display-definition.json",
        root / "definition" / "mlb-classic" / "fonts",
        root / "fixtures" / "project.json",
    )


def _logo_data(tone=None):
    data = []
    for i in range(256):
        x, y = i % 16, i // 16
        rgb = (0, 0, 0) if tone == 'black' else (16, 32, 64) if tone == 'dark' else (20, 110, 255)
        alpha = (0 if x < 2 or y < 2 or x > 13 or y > 13 else 128 if x % 2 else 255) if tone else 255
        data.extend((*rgb, alpha))
    return data


def verify_frames(root: Path, output_dir: Path) -> dict[str, Any]:
    definition_path, fonts_dir, _ = _paths(root)
    definition = _json(definition_path)
    games = _json(root / "fixtures" / "demo-day.json")
    standings = _json(root / "fixtures" / "demo-standings.json")
    frame_cases = _json(root / "fixtures" / "expected-render-frames.json")
    fonts = {
        name: parse_bdf((fonts_dir / f"{name}.bdf").read_text(encoding="utf-8"))
        for name in ("4x6", "5x7", "6x10")
    }
    by_game = {game["gameId"]: game for game in games}
    standings_snapshot = standings[0]
    by_team = {row["team"]["abbr"]: row for row in standings_snapshot["teams"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for frame_case in frame_cases:
        game = by_game.get(frame_case.get("gameId"))
        standing_team = by_team.get(frame_case.get("standingAbbr"))
        asset_key = None
        away_logo_asset_key = None
        home_logo_asset_key = None
        assets: dict[str, Any] = {}
        if frame_case.get("logo") and standing_team:
            asset_key = f"team-logo:{standing_team['team']['id']}:16"
            assets[asset_key] = {
                "width": 16,
                "height": 16,
                "data": _logo_data(frame_case.get("logoTone")),
            }
        if frame_case.get("gameLogos") and game:
            away_logo_asset_key = f"team-logo:{game['away']['id']}:16"
            home_logo_asset_key = f"team-logo:{game['home']['id']}:16"
            game_logo = {
                "width": 16,
                "height": 16,
                "data": _logo_data(frame_case.get("logoTone")),
            }
            assets[away_logo_asset_key] = game_logo
            assets[home_logo_asset_key] = game_logo
        started = perf_counter()
        frame = render_scene(
            definition,
            frame_case["scene"],
            fonts,
            game=game,
            standings=standings_snapshot if standing_team else None,
            standing_team=standing_team,
            logo_asset_key=asset_key,
            away_logo_asset_key=away_logo_asset_key,
            home_logo_asset_key=home_logo_asset_key,
            favorites=("WSH", "PHI"),
            elapsed_ms=frame_case["elapsedMs"],
            now="2026-07-15T17:05:00-04:00",
            assets=assets,
            transport_held=bool(frame_case.get("transportHeld")),
            overrides={"layoutPreset": frame_case["layoutPreset"]} if frame_case.get("layoutPreset") else None,
        )
        elapsed_ms = (perf_counter() - started) * 1000
        digest = hashlib.sha256(frame.data).hexdigest()
        (output_dir / f"{frame_case['name']}.png").write_bytes(encode_rgba_png(frame.width, frame.height, frame.data))
        results.append({
            "name": frame_case["name"],
            "expectedSha256": frame_case["sha256"],
            "actualSha256": digest,
            "match": digest == frame_case["sha256"],
            "renderMs": round(elapsed_ms, 3),
        })
    arcade_results = []
    for case in _json(root / 'fixtures' / 'arcade-replays.json'):
        state = create_game(case['kind'], case.get('seed', 727))
        state.update(case.get('patch', {}))
        for op in case['operations']:
            action = op.get('action')
            if action == 'start': state = start_game(state)
            elif action == 'swing': state = swing(state)
            elif action in ('up', 'down', 'left', 'right'): state = steer_snake(state, action)
            if op.get('press'): state = press_game(state, op['press'])
            for _ in range(op.get('ticks', 0)): state = step_game(state, set(op.get('held', [])))
        started = perf_counter()
        frame = arcade_frame(state, fonts['4x6'], case.get('paused', False))
        digest = hashlib.sha256(frame.data).hexdigest()
        arcade_results.append({'name': case['name'], 'expectedSha256': case['sha256'],
            'actualSha256': digest, 'match': digest == case['sha256'],
            'renderMs': round((perf_counter() - started) * 1000, 3)})
    nfl_results = []
    hashes = iter(_json(root / 'fixtures/nfl-frame-hashes.json'))
    for game in _json(root / 'fixtures/nfl-demo.json'):
        for layout in ('rows','compact'):
            for stale in (False,True):
                expected = next(hashes)
                started = perf_counter()
                frame = nfl_frame(game,fonts,layout,stale)
                elapsed = round((perf_counter()-started)*1000,3)
                digest = hashlib.sha256(frame.data).hexdigest()
                nfl_results.append(dict(name=f"NFL-{game['id']}-{layout}-{stale}", expectedSha256=expected,actualSha256=digest,match=digest==expected,renderMs=elapsed))
    nfl_logo_results = []
    hashes = iter(_json(root / 'fixtures/nfl-logo-frame-hashes.json'))
    for game in _json(root / 'fixtures/nfl-demo.json'):
        for layout in ('rows', 'compact'):
            for stale in (False, True):
                for tone in (0, 20, 80):
                    data = [v for i in range(256) for v in (tone, 2*tone, 3*tone, (0, 64, 128, 255)[i%4])]
                    assets = {f"team-logo:nfl:{team['id']}:16": {'width':16, 'height':16, 'data':data}
                              for team in (game['away'], game['home'])}
                    expected = next(hashes)
                    started = perf_counter()
                    frame = nfl_frame(game, fonts, layout, stale, assets=assets)
                    elapsed = round((perf_counter() - started)*1000, 3)
                    digest = hashlib.sha256(frame.data).hexdigest()
                    nfl_logo_results.append(dict(name=f"NFL-logo-{game['id']}-{layout}-{stale}-{tone}",
                        expectedSha256=expected, actualSha256=digest, match=digest==expected, renderMs=elapsed))
    max_render_ms = max((result["renderMs"] for result in results + arcade_results + nfl_results + nfl_logo_results), default=0)
    passed = all(result["match"] for result in results + arcade_results + nfl_results + nfl_logo_results) and max_render_ms <= 50
    report = {
        "schemaVersion": "1.0",
        "status": "pass" if passed else "fail",
        "frames": results,
        "arcadeFrames": arcade_results,
        "nflFrames": nfl_results,
        "nflLogoFrames": nfl_logo_results,
        "maxRenderMs": max_render_ms,
        "frameBudgetMs": 50,
        "pixelTolerance": 0,
    }
    (output_dir / "verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
