# Raspberry Pi tips

Lessons from running Pixelboard every day on a Raspberry Pi 3 A+ with an
Adafruit RGB Matrix HAT/Bonnet and two 64×32 P4 panels. If your build behaves
differently, please open an issue with what you found.

## A steady picture (flicker)

The `rpi-rgb-led-matrix` library refreshes the panels from a realtime thread,
and on a Pi 3 A+ anything that competes with that thread shows up as flicker or
"breathing". On the original build the measured refresh rate swung between
about 73 and 185 Hz. These changes brought it to a steady 120–150 Hz.

**Panel settings.** These are the `panel` section of the device's
`config/runtime-config.json`, and they are already the defaults for new
installs:

```json
"panel": {
  "hardwareMapping": "adafruit-hat",
  "gpioSlowdown": 2,
  "pwmBits": 7,
  "pwmLsbNanoseconds": 100,
  "limitRefreshRateHz": 150
}
```

Capping the refresh rate makes it *steady*, which matters more to your eyes
than a higher peak. Add `"showRefreshRate": true` temporarily to print the
measured rate.

**Give the refresh thread its own CPU core.** The service unit already sets
`CPUAffinity=0 1 2`. Pair it with `isolcpus=3` at the end of the single line
in `/boot/firmware/cmdline.txt`, then reboot. The library pins its refresh
thread to the highest core, which is then uncontended.

**Turn off onboard audio.** It competes with the panel for the same hardware.
Add `dtparam=audio=off` to `/boot/firmware/config.txt`, and add
`blacklist snd_bcm2835` to `/etc/modprobe.d/blacklist-rgb-matrix.conf`.

**Seat the HAT firmly.** On the original build, the top half of the panel lost
its red and green ("blue up top") and flickered more until the HAT was pushed
fully onto the GPIO header. If that comes back, reflow the header's solder
joints.

**The best fix is hardware.** Most remaining flicker on the Adafruit HAT comes
from not using the Pi's hardware PWM. Solder the jumper between **GPIO4 and
GPIO18** on the HAT, then set `"hardwareMapping": "adafruit-hat-pwm"`. A
separate 5 V supply for the Pi (never powered through the panel supply) also
helps.

## The service runs as root on purpose

By default `rpi-rgb-led-matrix` drops to the `daemon` user right after it
starts the panel. Pixelboard's updater and admin panel need root afterwards
(to stage releases and restart the service), so the runtime keeps root unless
you set `"dropPrivileges": true` in the `panel` section. If updates fail with
permission errors, check which user the service is actually running as:

```bash
sudo cat /proc/$(systemctl show -p MainPID --value scoreboard.service)/status | grep Uid
```

It should print `Uid: 0 0 0 0`.

## How updates work

- **Check for Updates** in the admin panel asks GitHub for the latest `main`
  with a read-only `git ls-remote`, so it never needs write access to the
  checkout.
- **Apply Update** runs `scripts/update-device.sh` from the source checkout
  named in `/etc/pixelboard/source-repo` (the installation guide sets this
  up). It pulls `main` as the checkout's owner, stages a new release under
  `/opt/pixelboard/releases/`, verifies every reference frame within the 50 ms
  budget, switches the `/opt/pixelboard` link, and rolls back if the new
  release doesn't report healthy.
- Your device's `config/` (settings and panel tuning) carries forward to each
  new release. History, arcade progress, the household PIN and other state
  live in `/var/lib/pixelboard`, which updates never touch.
- If git ever complains about permissions on `.git` (for example
  `cannot open '.git/FETCH_HEAD'` after something ran git with `sudo`), give
  the checkout back to its owner:
  `sudo chown -R <user>:<user> ~/pixelboard-source`. The updater also repairs
  `.git` ownership each time it runs.

## Handy checks

```bash
# Service health and installed build
curl -s http://pixelboard.local:8123/status | python3 -m json.tool | head -40

# Live logs
journalctl -u scoreboard.service -f

# Panel geometry, color channels and controller input (stops the display while it runs)
sudo systemctl stop scoreboard.service
sudo env PYTHONPATH=/opt/pixelboard/runtime /opt/pixelboard/.venv/bin/python -m scoreboard_device --root /opt/pixelboard diagnose
sudo systemctl start scoreboard.service
```
