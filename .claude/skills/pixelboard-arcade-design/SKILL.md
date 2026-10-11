---
name: pixelboard-arcade-design
description: Use when deciding what an arcade game or arcade screen for Pixelboard should look like, how it should feel, or how big a feature should be: designing for the 128x32 LED panel and the 8BitDo Zero 2 remote, pixel art and text layout, colour on LEDs, tuning game physics with simulated players, kid-friendly difficulty, and scoping work in playable stages. Use with pixelboard-arcade-games for the build mechanics.
---

# Designing arcade games for a 128x32 panel

The players are often kids, on a wall-mounted LED panel with a
small Bluetooth controller. Good games here are instantly readable, forgiving
to start, and give a reason to play again. Every lesson below came from
building Neon Rider.

## Find the balance: scope in playable stages

- **Build the smallest fun loop first** (Rider v1 was one button, hills,
  flips and crashes). Ship it and let the kids play it. Their feedback beats
  guesses: they asked for the shop and Happy Hour, not for physics
  changes.
- **Split big ideas into stages that are each playable**, such as batting
  only → hits and running → pitching → innings. Each stage gets its own
  fixtures and its own ship.
- **Mock before building:** render 4–8 sample screens with the real
  renderer and the fixture tool's `--preview`, then get feedback. That
  costs minutes; rebuilding after a "that's unreadable" costs hours.
- **Rough sizes** (Python + TS + tests): a Snake/Pong-sized game is
  150–250 lines; Rider with physics was about 900 including fixtures; a
  multi-view sports game is 5–10× Rider, so stage it.
- **Prefer depth through options over complexity:** styles, themes and
  unlocks reuse one game loop and delight kids cheaply.

## The canvas

- 128x32 pixels, roughly 4:1. Wide side-scrolling views, a flattened field
  seen from above, or a behind-the-player view all fit. Tall views do not.
- **Text:** 4x6 font, 4 px per character, so 32 characters fit and about 30
  is comfortable. Four text rows sit at **y = 1, 9, 17, 25**; y = 0 clips the
  top pixel with `_draw_text`. Inside games, the HUD takes row 0 and leaves
  about 25 px of play area.
- **Sprites:** objects under 3 px are dots, so give anything the player
  must track at least 3–4 px. Rider's car is 8x4. Draw sprites as string art
  (`'BBG'` rows with letter roles) so both languages share one picture and
  recolouring is a lookup.
- **Rotation:** 16 headings (22.5° steps) read fine at this size. Use the
  integer `COS16`/`SIN16` tables.
- **Keep the subject on screen:** Rider lowers the world ("lift") during
  high jumps rather than letting the car leave the top edge. Check the
  extremes in previews: highest jump, lowest valley, longest text.
- **Smooth lines:** round fixed-point positions to pixels; flooring leaves
  one-pixel notches at curve peaks.

## Colour on LEDs

- The panel is black where nothing is drawn, and LEDs make saturated
  colours pop. Use dark backgrounds with bright outlines (neon line plus
  dim glow plus very dark fill).
- Fills around (15, 5, 35) read as "dark terrain" without washing out.
  Below about 10 per channel, colours are effectively off.
- **Text must be bright:** hints at (25, 61, 56) were unreadable; use
  around (90, 140, 130) or brighter. Gold (255, 201, 58) means
  reward/selection, teal means player/self, white means information.
- Don't rely on one colour difference alone to carry meaning (for example
  Happy Hour also shows "3X").
- Quiet hours dim the panel, so test that the important pixels survive at
  low brightness.

## Controls (8BitDo Zero 2)

- D-pad, A, B, X, Y, L, R, Start, Select. **Y** (Home) and **Select**
  (leave) are reserved. **R** is free inside games.
- **One-button cores are best for young kids:** hold A to drive, release to
  coast, hold in the air to flip. Add depth with timing and holding, not
  more buttons.
- Use the same meaning everywhere: A go/confirm, B back, Start pause, X
  restart, D-pad move/browse.
- The remote is Bluetooth: expect around 30–60 ms of input latency. Timing
  windows tighter than about 50 ms will feel unfair.

## Tuning feel with simulated players

Before showing a game, simulate policies over several seeds (3000 steps is
one minute of play):

- **idle** (no input): should be safe, not a crash or a fail.
- **naive** (hold the main button forever): should end reasonably soon so
  there is something to learn. Rider's hold-A crashed in about 8–13 s.
- **sensible** (Rider: gas on ground, release in air): should survive for a
  long time. Kids should be able to play without dying constantly.
- **skilled/oracle** (looks ahead to plan tricks): should be able to reach
  the bonus mechanics. If even the oracle can't flip, the window is too
  short.

Measure the things that matter: time to fail, events per minute (Rider
counted jumps), airtime distribution versus the time a trick needs,
collectables per minute (which sets shop prices), and the highest and lowest
on-screen positions.

Lessons from Rider:

- **Auto-help must target the forgiving thing:** levelling toward flight
  direction made flat landings crash; levelling toward the ground below
  fixed it.
- **Integer friction needs a ceiling division** (`(v + 127) // 128`).
  Otherwise slow objects never stop.
- Lower top speed killed jumps entirely; speed, gravity and terrain
  curvature interact, so re-run the bots after every constant change.

## Lessons from Big League and Soccer

- **Sports AI is a few rules, not a planner:** "nearest fielder intercepts
  the predicted ball, others cover bases, throw where the throw beats the
  runner" gave natural double plays. Re-plan only when the ball passes the
  chaser's spot, because planning every step is too slow for the Pi.
- **Fast objects tunnel:** a 3.5 px/step shot skipped past a 3 px keeper.
  Move fast balls in sub-steps and check catches in each one.
- **Bots find exploits kids will find:** idle defenders camping on the
  keeper stole every clearance (fixed: rivals wait outside the box). Chasing
  and mashing A won every match (fixed: dash tackles miss half the time).
  Run idle, sensible and mash policies for any action game.
- **A contact model beats exact physics for batting:** map timing error and
  aim distance to quality, then quality to launch type. Generous windows
  (foul over 120 ms, miss over 170 ms) suit Bluetooth latency. Tune runs per game
  (about 2–3 a side for 3 innings) by fielder/runner/throw speeds and runner risk.
- Give the computer side a **guess** (pitch speed) so changing speeds and
  locations is a real strategy for kids.
- **Two views beat one cramped view:** behind-the-batter for the pitch, a
  flattened top-down field (x 0.27 px/ft, y 0.085 px/ft) once the ball is hit.

## Lessons from Rainbow Toot Unicorn

- **The panel has no speaker, camera or microphone.** Replace sound with
  bubbles, action words, a ticker and full-screen scenes. Anything "physical"
  (dance, shout) is honor system confirmed with A.
- **Never flash the whole panel white:** the Pi shares the panels' supply and
  the players are kids. Flash borders or text at 1–3 Hz instead.
- **Effects need about 100 ms or more:** the panel redraws at about 20 fps.
- Spawn tables must be explicit per item: cumulative thresholds silently
  changed apple odds when star odds moved.
- **Traps that end the game must be avoidable on purpose:** the 3D glasses
  always fly high, so a unicorn on the ground runs under them.
- Write catchphrases exactly as players say them ("SIX SEVEN", never
  "sixty-seven").

## Rewards and retention

- **No names on anything.** Player profiles were proposed and rejected
  because ranking individual kids against each other upset them, so progress
  is shared by the household: one gem jar, one style, one unnamed high score
  per game. Discuss in an issue before adding anything that ranks or labels
  individual players.
- **Currency to style shop:** price items from measured earning rates.
  Rider earns about 30–60 gems per good minute, so the cheapest items cost
  about one run and the showpiece (UFO 300) costs many.
- **Timed events** (Happy Hour) create anticipation; show a countdown on the
  menu. Never during quiet hours.
- Celebrate on the over screen ("NEW HIGH SCORE!", "+12 GEMS") on the bottom
  row, below the shared overlay.
- Games are closed during quiet hours by design, so keep that true for new
  games.
