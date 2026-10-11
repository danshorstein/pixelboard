# Versioned schema decisions

All contracts use JSON Schema draft 2020-12. The original four M1 entities
remain compatible with `1.0`; project and display-definition revisions add
the backward-compatible mixed-content surface. Display definition `1.2` adds
definition-owned source-health overlays without adding executable behavior.

The design documents leave three integration details illustrative rather than
normative. M1 resolves them as inert data conventions so the renderer never
needs layout-specific hard-coding:

- Display element `color` and `font` values may reference declared parameters
  with `$colors.<name>` and `$fonts.<name>` tokens.
- `visibleWhen` links an element to one boolean `$elements.<name>` parameter.
- `presets` holds complete alternate game-scene sets selected by
  `layoutPreset`; `teamColors` is definition-owned data used only when the
  declared `useTeamColors` parameter is enabled.
- `standings-state.schema.json` is a fifth first-class content contract. It
  carries one ordered division snapshot and never masquerades as game data.
- Sprite elements may use a static `asset` or a safe `bind` that resolves to an
  asset key. This lets an optional logo pack enhance a scene without making a
  licensed mark part of the public definition.
- `asset-pack.schema.json` requires exact dimensions, source, usage status, and
  SHA-256 for every optional optional logo.
- Validation, verification, readiness, and artifact-manifest reports are also
  versioned contracts. A build can claim `ready` only when validation and the
  byte-exact renderer harness both pass.

Game-state optional detail fields remain optional and nullable. Core identity,
teams, status, start times, and fixture-source metadata are required. This lets
the deliberately incomplete fixture omit `bases` and `count` entirely while
remaining valid.

Conditions accept one path-to-literal comparison only. They cannot call
functions, chain expressions, or execute code.
