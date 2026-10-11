# Controls

Pixelboard is built around the **8BitDo Zero 2**, a small Bluetooth
controller, used in **keyboard mode**. Every button sends a keyboard key, and
the device reads it through Linux evdev. Other controllers can work if you map
their key codes (see [Using a different controller](#using-a-different-controller)).

## Pair the controller

1. On the Pi, open `bluetoothctl`, then run `power on`, `agent on` and `scan on`.
2. Hold **R + Start** on the controller to switch it on in keyboard mode.
3. When `8BitDo Zero 2 gamepad` appears, run `pair <address>`,
   `trust <address>` and `connect <address>` with the address it shows.
4. After that, pressing **Start** once turns the controller on and reconnects
   it. Hold **Start** for 3 seconds to turn it off.

The device looks for the input device by name. On Linux the keyboard profile
appears as **`8BitDo Zero 2 gamepad Keyboard`**, and that name must match
`bluetoothRemote.deviceName` in the device's `config/runtime-config.json`.
If Bluetooth says the controller is connected but the board says it isn't,
the name is the first thing to check.

## Scoreboard

| Button | What it does |
| --- | --- |
| **A** | Next screen; from the Home clock, back to scores |
| **B** | Hold the current game, or go back to live rotation |
| **Y** | Home clock (from anywhere: scores, menus or the arcade) |
| **Select** | Main menu (one press; you never need to hold it) |
| **R** | Team-schedule card. A moves to the next card, B holds |

During quiet hours the first press only wakes the board. Press again to act.

## Main menu

Select opens the menu: **Scoreboard**, **Arcade Games**, **Settings**,
**NFL Settings**, **Pick NFL Games**, **NFL Favorites**, **Past Scores** and
**Home Clock**.

- Up/Down chooses, A opens, B goes back. Select or B from the top closes the
  menu without saving.
- In **Settings**, Left/Right changes a value, X previews it, and A saves.
  Unsaved changes are dropped after 60 seconds without input or if the
  controller disconnects.
- In the NFL pages, A toggles a choice. Pick **Save Changes** to keep them.

## Past scores

Select → **Past Scores** → A opens a date picker. Left/Right moves a day and
L/R moves a week. A shows every final MLB and NFL game for that date, then A
advances, B holds, and X returns to live scores. Past scores go back to live
after 10 minutes.

## Arcade

| Button | What it does |
| --- | --- |
| **D-pad** | Move, or choose a game |
| **A** | Start, or the game's main action |
| **B** | Back to the game list (in Rainbow Toot Unicorn, B throws a bomb; press Start then B, or Select, to leave) |
| **X** | Restart the game |
| **Start** | Pause |
| **Select** | Leave the arcade |

Each game's own buttons are in [the arcade guide](ARCADE.md).

## Using a different controller

Any Bluetooth or USB device that shows up as a Linux keyboard can work. Find
its name and key codes on the Pi:

```bash
for path in /sys/class/input/event*/device/name; do printf '%s: ' "$path"; cat "$path"; done
sudo evtest   # pick the device, press each button, read the EV_KEY codes
```

Then edit the `bluetoothRemote` section of the device's
`config/runtime-config.json`: set `deviceName` to the exact name, and set
`keyCodes` (and `nextKeyCode`/`holdKeyCode` for A/B) to the codes you read.
Restart `scoreboard.service`. Updates keep the device's own config. The
defaults for the Zero 2 are:

| Button | Key | Code |
| --- | --- | ---: |
| Up / Down / Left / Right | `KEY_C` / `KEY_D` / `KEY_E` / `KEY_F` | 46 / 32 / 18 / 33 |
| A / B | `KEY_G` / `KEY_J` | 34 / 36 |
| X / Y | `KEY_H` / `KEY_I` | 35 / 23 |
| L / R | `KEY_K` / `KEY_M` | 37 / 50 |
| Select / Start | `KEY_N` / `KEY_O` | 49 / 24 |

Don't run `evtest --grab` while the service is running, because it stops the
service from seeing the buttons. The service's view of the controller is under
`bluetoothRemote` in `http://pixelboard.local:8123/status`.
