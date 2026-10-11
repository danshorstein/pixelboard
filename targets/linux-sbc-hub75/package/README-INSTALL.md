# Raspberry Pi installation

This installer expects a generated Pixelboard device package and a Raspberry
Pi running Raspberry Pi OS Lite 64-bit. It builds the pinned HUB75 driver,
checks the package, installs the service, and verifies `/status` before
switching the active release.

## Install

1. Generate the device package in Pixelboard Studio and transfer the archive
   to the Pi.
2. Extract it and enter the extracted directory.
3. Install it:

   ```bash
   sudo ./install.sh
   ```

4. Open `http://pixelboard.local:8123/` from a device on the same trusted
   network. If local name discovery is unavailable, use the Pi's LAN address.
5. Connect dashboard updates to the public source repository. Run these as
   the normal Pi user from a shell:

   ```bash
   git clone --branch main https://github.com/danshorstein/pixelboard.git "$HOME/pixelboard-source"
   sudo install -d -o root -g root -m 0755 /etc/pixelboard
   printf '%s\n' "$HOME/pixelboard-source" | sudo tee /etc/pixelboard/source-repo >/dev/null
   ```

   The clone stays owned by the normal Pi user; the pointer file is root-owned.
   This lets the updater pull public `main` without GitHub credentials.
6. Retrieve the unique six-digit household PIN on the Pi:

   ```bash
   sudo /opt/pixelboard/.venv/bin/python -m scoreboard_device --root /opt/pixelboard broadcast-pin show
   ```

The PIN protects dashboard settings, controls, messages, and software updates.
Store it privately. Do not include it in URLs, screenshots, logs, or source.

## Update

Use **Check for Updates** and **Apply Update** in the dashboard, then enter the
household PIN. The updater pulls `main` from the configured GitHub repository,
stages a verified release, restarts the service, and rolls back if the health
check fails. If the source pointer is missing, create the root-owned directory
and pointer shown in step 5. Verify the repository path is readable by the Pi
user.

The service keeps settings and history in `/var/lib/pixelboard`. Back up this
directory before changing hardware or replacing the device.

## Troubleshooting

- Check `http://pixelboard.local:8123/status` for service health and installed
  build identity.
- If the dashboard asks for a PIN, retrieve it locally with the command above.
- If update health verification fails, the installer restores the prior
  release. Review the installer output on the Pi before retrying.
- Run the package's `scoreboard-device diagnose` command for panel geometry,
  color-channel, and input checks.
