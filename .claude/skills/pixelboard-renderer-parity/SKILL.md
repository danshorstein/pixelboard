---
name: pixelboard-renderer-parity
description: Use whenever changing shared_ts/renderer.ts, shared_py/renderer.py, or any sibling pixel-frame module (shared_py/fireworks_frame.py, shared_py/reveal_frame.py, shared_py/recap_frame.py, shared_ts/fireworks.ts, and any future one) in Pixelboard. Enforces byte-identical TS/Python output for anything shown in both runtimes, covers when a device-only frame is exempt from a TS twin, and covers the JS-vs-Python rounding gotcha that actually broke this once.
---

# Renderer parity (TS ⇄ Python)

This project renders the same scoreboard on two runtimes: the browser Studio
(TypeScript, `shared_ts/renderer.ts`) and the physical device
(Python, `shared_py/renderer.py`). **Every pixel a viewer can see must be
byte-identical between the two.** This is not a style preference — it's
tested (`shared_ts/frame-parity.test.ts`, `tests_py/test_renderer_parity.py`,
`fixtures/expected-render-frames.json`) and the tests must both be green
before any renderer change lands.

## The rule

Any change to what gets drawn **in both runtimes** — a new scene, a new
fallback, a new frame generator (fireworks) — must be implemented in
**both** `shared_ts/` and `shared_py/`, with the same behavior, before it's
considered done. "I'll port it later" is how the "P PITCHER B BATTER"
placeholder-text bug shipped in the first place.

## Device-only frames are exempt from a TS twin

The rule is "every pixel a *viewer* can see is byte-identical" — and some
frames are only ever shown on the physical panel, never in the browser
Studio. Those legitimately have **no** `shared_ts/` counterpart and **no**
golden-fixture entry:

- `shared_py/reveal_frame.py` — the boot surprise's staged text (plays at
  boot or from the dashboard's announcement controls only).
- `shared_py/recap_frame.py` — the morning recap/next-game cards (play on
  the panel during the configured morning window only).

Both keep themselves *out* of the parity surface by delegating all pixel
drawing to `create_reveal_text_frame` (which itself only uses
`renderer.py`'s tested `_draw_text`) — they add **no new pixel math**, so
there's nothing to diverge. If you add another device-only frame, do the
same: compose from existing tested primitives rather than writing fresh
blend/position arithmetic. If it *must* have new pixel math, it needs the
full A/B byte-diff treatment below even without a TS twin, plus a
`tests_py/` hash test. And the moment a device-only frame gains a Studio
preview, it becomes a two-runtime frame and this whole skill applies.

## The gotcha: JS `Math.round` vs Python `round()`

`Math.round` rounds half **away from zero** (toward +Infinity for positive
numbers). Python's built-in `round()` rounds half **to even** (banker's
rounding). For most pixel math this never surfaces because exact `.5`
boundaries are rare — but it *will* surface eventually, and when it does the
divergence is not a rounding-by-one-pixel curiosity, it silently changes
which pixels get touched by a blend operation, producing visibly different
output at a handful of pixels with no obvious cause.

This actually happened porting `createFireworksFrame` → `create_fireworks_frame`
(`shared_py/fireworks_frame.py`). The fix was a local `_js_round` helper:

```python
def _js_round(value: float) -> int:
    """Matches JS Math.round (half rounds toward +Infinity), unlike Python's
    round() (half rounds to even)."""
    return math.floor(value + 0.5)
```

Use this (or an equivalent) for **any** value ported from a TS `Math.round`
call in pixel-position or color-blend math. Don't assume Python's `round()`
is a safe drop-in.

Also check `Math.trunc` vs Python `int()` when porting — these DO match
(both truncate toward zero for positive and negative), so `PixelBuffer`'s
`set_pixel`/`fill_rect`/`draw_line` (which use `int()` internally) are safe
to hand raw floats — don't pre-round before calling them, or you'll double
apply rounding and get a different, also-wrong answer. Trace what the TS
source actually passes into `setPixel`/`drawLine`/etc. — sometimes it's a
raw float (relying on internal `Math.trunc`), sometimes it's pre-rounded
with `Math.round`. Match that exactly, don't guess.

## How to verify byte-parity yourself (not just trust the tests)

Before trusting a port, do a direct A/B hash comparison across a spread of
inputs — this is how the rounding bug above was actually found, *before*
writing the permanent regression test:

```bash
# TS side: dump raw frame bytes to a file from a throwaway vitest test
# (write frame.data via Buffer.from(frame.data) with node:fs, run with
# npx vitest run <file>, then delete the throwaway test)

# Python side:
.venv/bin/python -c "
from shared_py.fireworks_frame import create_fireworks_frame
frame = create_fireworks_frame(128, 32, 1000)
open('/tmp/py_frame.bin', 'wb').write(bytes(frame.data))
"

# Compare:
python3 -c "
a = open('/tmp/ts_frame.bin','rb').read()
b = open('/tmp/py_frame.bin','rb').read()
diffs = [i for i in range(len(a)) if a[i] != b[i]]
print('diffs:', len(diffs))
"
```

Zero diffs across several different input values (not just one) is the bar.
Test at least 4-6 different parameter values (e.g. different `elapsedMs`) —
a rounding bug can hide at one value and appear at another.

## After confirming parity, freeze it as a test

Add a hardcoded-hash regression test in `tests_py/` (see
`tests_py/test_fireworks_frame_parity.py` for the pattern: a dict of
`{input: expected_sha256}` computed once from the verified-matching output,
asserted forever after). This is cheaper than a cross-language test harness
and catches any future regression in either implementation.

## Golden frames for scene-based rendering

If the change touches an actual `DisplayScene` (not a standalone frame
generator like fireworks), you also need to regenerate
`fixtures/expected-render-frames.json` — see `shared_ts/frame-parity.test.ts`
and `tests_py/test_renderer_parity.py` for how cases are structured
(`gameId`, `scene`, `elapsedMs`, `sha256`, etc.). Don't hand-edit the sha256
values; render and capture them for real, from both sides, and confirm they
match each other before writing either into the fixture.

## Studio quiet-hour preview alignment (known open gap)

The browser Studio does **not** yet visibly dim or sleep to match the
device's actual quiet-hours behavior (`_render` in the device runtime sets
brightness / blanks; the Studio preview ignores it). If you're adding a Studio-side
quiet-hours preview, the device is the reference — match `_render`'s
precedence (reveal → quiet+sleep blank → brightness → fireworks → recap →
rotation), don't invent a second interpretation.

## Don't skip this because "it's just text"

The pitcher/batter placeholder bug and the fireworks rounding bug were both
found by someone actually diffing bytes, not by reading the code and
deciding it looked equivalent. Small formatting/wording changes are exactly
where a one-language-only edit slips through, because it "obviously" doesn't
need porting — it does.
