# Pixelboard

Pixelboard is a configurable sports display for RGB LED matrices. It combines
live scores, standings, schedules, a browser-based setup studio, local device
controls, and small arcade games on a Raspberry Pi.

## Features

- MLB and NFL scores, standings, final scores, and scoring alerts
- Configurable rotation, favorites, brightness, quiet hours, clock, and alerts
- Optional team schedule and practice cards from an iCalendar subscription
- Local dashboard with display preview and device settings
- Arcade games and a configurable celebration screen
- Raspberry Pi/HUB75 runtime with simulator and verification tools

The project is an unofficial fan project. It is not affiliated with MLB, the
NFL, their teams, or data providers. Team names and logos are owned by their
respective rights holders. Live feeds and optional images depend on external
services; text fallbacks are available.

## Run the browser studio

Requirements: Node.js, npm, Python 3, and `venv` support.

```bash
npm ci
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
npm run dev
```

The studio includes demo, historical, and empty-day modes. The default project
and fixtures use synthetic team-calendar data; add your own preferences and
calendar locally.

## Build and install for Raspberry Pi

The documented prototype uses two chained 64×32 P4 HUB75 panels, a Raspberry
Pi 3 A+, an RGB Matrix Bonnet, and a Bluetooth keyboard-style remote. The
accepted rear enclosure uses three printed sections. See the
[hardware inventory](hardware/README.md) and
[assembly guide](targets/linux-sbc-hub75/package/ASSEMBLY-GUIDE.md) for the
known parts and physical arrangement.

Generate the device package from the studio's Setup view, transfer it to a
Raspberry Pi running Raspberry Pi OS Lite, and follow the
[device installation guide](targets/linux-sbc-hub75/package/README-INSTALL.md).
The repository's install template is not itself a complete device package.

## Develop and verify

```bash
npm test
npm run test:py
```

See [contributing](CONTRIBUTING.md) for change and verification guidance.

## Project licenses

- Software: [MIT](LICENSE)
- Original hardware designs: [CERN-OHL-S-2.0](hardware/LICENSE)
- Original documentation and project images: [CC BY 4.0](docs/LICENSE)

Third-party code, fonts, data, and marks retain their own notices and terms;
see [third-party notices](targets/linux-sbc-hub75/package/THIRD_PARTY_NOTICES.md).
