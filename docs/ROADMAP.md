# Roadmap

Ideas that are planned but not built. If you want to take one on, open an
issue first so the work isn't duplicated.

## 1. Wi-Fi setup from a phone (next up)

**Problem.** Wi-Fi is set once, when the SD card is flashed. Take the board
to a new house or change routers and it still starts, with the clock and
arcade working, but scores say `DATA OFFLINE - CHECK WIFI`, and nothing can be
reached to fix it without a keyboard and screen or pulling the SD card.

**What the person would see**

1. Plug the board in somewhere new. After about a minute without a known
   network, the panel shows `WIFI SETUP`, a hotspot name such as
   `PIXELBOARD-4F2A`, its password, and a QR code that joins the hotspot.
2. The phone joins and a setup page opens on its own (like a hotel sign-in
   page). The panel also shows `OPEN 10.42.0.1` in case it doesn't.
3. The page lists nearby networks, strongest first, plus "Other…" for hidden
   ones. Pick one and type its password. Time zone (prefilled from the phone)
   and favorite teams are optional.
4. The panel shows `CONNECTING…`, then `CONNECTED!` with the dashboard address,
   then scores. A wrong password brings setup back with the error on both the
   panel and the page.

Setup mode can also be opened from the controller (Select → Settings →
Wi-Fi Setup) or from the admin panel, to change networks before the old one
goes away.

**Design**

| Decision | Choice | Why |
|---|---|---|
| Networking | NetworkManager (`nmcli`), the default on current Raspberry Pi OS | It can save networks, scan, and run a hotspot with built-in DHCP/DNS (`ipv4.method shared`), with nothing extra to install |
| Where it runs | A small separate `scoreboard-network.service` (`network_setup.py`) | Recovering the network shouldn't depend on the display runtime staying healthy, or the reverse |
| Panel screens | The service writes `state/network.json` atomically; the runtime shows it as a takeover screen, like the arcade | The runtime already reads `state/`. These frames are device-only, so no TypeScript twin is needed |
| Setup page | Served on port 80 on the hotspot only | Phones only pop up the sign-in page for port 80, and the page is unreachable from a home network |
| Pop-up page | A DNS rule pointing every name at the Pi while the hotspot is up, plus answers to the phone "is there internet" checks (`/hotspot-detect.html`, `/generate_204`, …) | That's what makes the page open by itself |
| QR codes | A Wi-Fi join code (`WIFI:T:WPA;S:…;P:…;;`), then a web-address code | A version 3 code (29×29) fits 32 rows at one LED per module, about 10 cm wide on P4 panels |
| Hotspot password | Random per device, made at first boot, kept in `state/`, shown only on the panel | Nobody nearby gets in without seeing the screen |
| Saved networks | Only ever added, never removed except by a deliberate "forget" | A typo during setup can't strand a board at a known place |

**When setup mode starts and stops**

```
boot
 └─ wait up to 90 s to join any saved network
     ├─ joined ─────────────────────────────► NORMAL
     └─ not joined → scan, save results ────► SETUP

NORMAL
 ├─ controller or admin panel "Wi-Fi Setup" ► SETUP
 └─ no saved network seen for 10 minutes ───► SETUP
    (a router reboot or short dropout must NOT trigger setup)

SETUP
 ├─ page submits network + password → hotspot down → try to join (up to 30 s)
 │    ├─ joined → save it (keep the old ones) ─► NORMAL, panel shows CONNECTED
 │    └─ failed → hotspot back up with the error shown
 ├─ every 5 minutes with no phone joined: drop the hotspot, rescan, and
 │    rejoin a saved network if it has come back
 └─ B or Select on the setup screen ───────► leave setup, keep trying saved networks
```

The Pi 3 A+ has one Wi-Fi radio, so it can't run the hotspot and join a
network at the same time. That's why it scans first and drops the hotspot
briefly to retry. Hotel-style sign-in networks, enterprise logins and
WPA3-only routers are out of scope, and the page should say so.

**Build steps**

1. `network.py`: a thin `nmcli` wrapper (list saved, scan, join, hotspot
   up/down, state, forget) with one injectable command runner so tests can fake
   it. Never log Wi-Fi passwords.
2. `network_setup.py`: the state machine above, with `state/network.json` as
   output and a small request file as input.
3. The setup page: one self-contained HTML page with no outside resources
   (the phone has no internet on the hotspot).
4. Captive-portal plumbing: the hotspot profile (`802-11-wireless.mode ap`,
   `ipv4.method shared`, WPA2-PSK, `10.42.0.1`), the DNS rule, and the
   "is there internet" answers.
5. Panel screens: setup steps with the Wi-Fi QR code alternating with the
   address QR code, `CONNECTING…`, `CONNECTED!`, and the error. Setup ranks
   above scores but below a playing surprise, and quiet hours don't blank it.
6. A **Wi-Fi Setup** item in the controller menu (`controller_settings.py`)
   and a "Change Wi-Fi" button in the admin panel behind the household PIN.
7. `install.sh` and `update-device.sh` install and enable the new unit, with a
   `network.setupMode: "auto" | "manual" | "off"` switch (default `auto`).
   Updates never touch saved networks.

**Testing.** Unit tests for `nmcli` parsing, every state-machine path, that
saved networks are never removed, that the hotspot password survives restarts,
and that the QR code fits in 32 rows. Then on a real Pi with a spare SD card:
an iPhone and an Android phone, a wrong password, a hidden network, 2.4 and
5 GHz, a router reboot (must not enter setup), the home network off for more
than 10 minutes, a power cut during setup, and readability from across the
room.

## 2. More than one board on a network

Every board is currently `pixelboard.local`. Give each its own ID at first
boot (for example from the Pi serial number) and use it for the hostname
(`pixelboard-4f2a.local`) and the setup hotspot name, with an optional display
name for the dashboard title and the arcade menu.

## 3. Updates from tagged releases

Devices currently follow `main`. Following signed, tagged releases instead
would let `main` move fast while boards only take tested versions, with the
updater checking the tag's signature before staging.

## 4. Controller pairing from the panel

Pairing currently needs `bluetoothctl` on the Pi. A **Pair Controller** step
in setup mode or the admin panel could scan, show the controller's name on the
panel, and pair and trust it.

## 5. A ready-to-flash SD card image

A Raspberry Pi OS Lite image with the runtime, the panel driver and Wi-Fi
setup mode already installed, so building one is: flash, plug in, scan the
QR code.

## 6. Hardware

- Test and document other Raspberry Pi models and panel sizes.
- A tested hardware-PWM build (the GPIO4–GPIO18 jumper), which should remove
  the last of the flicker described in [Pi tips](PI_TIPS.md).
