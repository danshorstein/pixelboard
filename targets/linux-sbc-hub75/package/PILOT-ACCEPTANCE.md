# Device acceptance checklist

Complete these checks on the assembled display before relying on it unattended.
Record the panel, power supply, and controller revisions with the results.

## Display and controls

- Confirm the two panels appear in the intended order with correct color order.
- Check text readability, brightness, flicker, and viewing angle in the final location.
- Test every remote button from the expected viewing distance.
- Verify live scores, final scores, schedules, and stale-data behavior.
- Confirm the dashboard PIN, settings saves, and software update flow.

## Power and unattended operation

- Confirm the Pi and panels use their separate regulated supplies.
- Check connector polarity, cable clearance, strain relief, and case temperature.
- Exercise quiet-hours dimming or sleep and the configured wake behavior.
- Run the display for at least 24 hours across game updates, a network outage,
  network recovery, and a reboot.
- Review `/status`, service health, and the installed build after the soak.

Record any failed check and correct it before unattended use.
