# The arcade

Press **Select**, choose **Arcade Games**, then use the D-pad to pick a game
and A or Start to play. In every game, **Start** pauses, **X** restarts,
**B** returns to the game list (except in the unicorn game, where B is a
bomb), and **Select** leaves the arcade. **Y** always goes to the Home clock.

The arcade closes during quiet hours. A game in progress is saved and the
panel shows ARCADE CLOSED.

## The games

### Neon Rider

Drive over endless neon hills. **Hold A** (or Right) to accelerate. Keep A
held in the air to backflip, and let go in time for the car to level out
before it lands. Landing a flip earns bonus gems. Crash and the run is over.
Cars, colors and tracks come from the Style Shop.

### Big League

Three innings of baseball against the Pi, with extra innings if it's tied
(the game ends as a tie after six). A half inning also ends after six runs.

- **Batting**: the D-pad moves your swing spot and **A** swings. Timing
  matters more than aim. Once the ball is in play, A sends your runners.
- **Pitching**: the D-pad aims, **L/R** picks a fastball, curve or change-up,
  **A** starts the meter and **A** again throws. Stop the meter in the middle.
  The Pi guesses your speed, so mix your pitches.
- A hit switches to a view of the whole field. **A** skips the line score
  between halves.

Gems: 3 per run you score, 10 more for a win.

### Soccer

3-on-3 against the Pi: you're teal, attacking to the right. The **D-pad** runs
whichever of your players is nearest the ball (diagonals work). With the ball,
**A** shoots when you face the goal (hold Up or Down to aim for a corner) or
kicks the way you're facing to pass. Without the ball, **A** is a dash
tackle, which misses about half the time. The ball bounces off the walls, so
play never stops. A tie after three minutes goes to a golden goal.

Gems: 5 per goal, 10 more for a win.

### Rainbow Toot Unicorn

The unicorn gallops on its own for two minutes.

- **A** toots a rainbow to fly up.
- **B** throws a bomb at beehives. You start with 3 and can collect more.
- **R** is a horn dash while you wear one or two headbands.

Collect **5 stars to win** and **10 for the grand prize** (the game stops at
10). Dodge hives and bee swarms, and eat apples for health. The fourth
headband stops everything for the **SIX SEVEN dance**: stand up, dance, and
press A when you're done. After that, every star brings a 10-second SIX SEVEN
shake. Avoid the **3D glasses**. They always fly high, and if you grab them
the unicorn turns into a 3D robot that crashes into six beehives in seven
seconds, and the game is over.

Gems: 2 per star, 10 more for a win, 50 more for the grand prize.

### Baseball, Snake and Pong

- **Baseball**: ten pitches. Press **A** to swing; three strikes and you're out.
- **Snake**: steer with the D-pad and eat the dots without hitting the
  walls or yourself. It speeds up as it grows.
- **Pong**: Up/Down moves your paddle. First to 5 points against the Pi wins.

## Gems, the Style Shop and Happy Hour

The whole household shares **one gem jar** and **one high score per game**
(Pong counts wins). There are no player names or profiles, on purpose. Gems
can also be added or removed from the Arcade card in the admin panel with the
household PIN, which is handy as a reward.

The **Style Shop** is the last item in the game list. Up/Down chooses a car,
color or track, Left/Right browses, A buys or uses an item, and B goes back.

| Cars | Colors | Tracks |
| --- | --- | --- |
| Buggy (free) | Teal (free) | Neon (free) |
| Truck 60 | Red 20 | Sunset 50 |
| Limo 90 | Gold 30 | Ice 70 |
| Bike 120 | Lime 30 | Lava 90 |
| UFO 300 | Blue 30 | Space 120 |
| | Rainbow 150 | Ballpark 150 |

**Happy Hour** is a 10-minute window every three hours when games earn triple
gems. The game list shows a countdown. It never falls inside quiet hours.

## Adding a game

Arcade games run on the Pi in Python and in the browser studio in TypeScript,
and the two must agree exactly: the same game state and the same pixels, step
by step. That makes every game reproducible from a short list of button
presses, and those replays are what the tests check.

The full recipe is in [`.claude/skills/pixelboard-arcade-games/SKILL.md`](../.claude/skills/pixelboard-arcade-games/SKILL.md),
and design advice for a 128×32 screen and a small controller is in
[`.claude/skills/pixelboard-arcade-design/SKILL.md`](../.claude/skills/pixelboard-arcade-design/SKILL.md).
Both are plain Markdown, written for people and for Claude Code alike. In short:

1. Write the rules in `shared_py/` and port them line for line to
   `shared_ts/`, with the picture in a matching `*_frame` module.
2. **Use integers only** in game state (fixed point, 1/256 px). Python `//`
   floors, so TypeScript uses `Math.floor(a / b)`. Python `%` is never
   negative, so TypeScript uses `((a % n) + n) % n`. Don't let `-0` into
   state, and break ties with explicit loops.
3. Add replay cases to `fixtures/arcade-replays.json` and fill in their
   expected states and frame hashes with
   `.venv/bin/python scripts/arcade_fixtures.py --update-missing`. Both test
   suites and the Pi installer check every case.
4. Wire the buttons in the device's `arcade.py`, and keep each frame under
   about 4 ms on a desktop, because the Pi 3 A+ is roughly ten times slower and
   the installer enforces 50 ms.
5. Tune with simulated players (idle, button-mashing and sensible) before
   asking real players.
