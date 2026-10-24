# Choose sports and teams

Version 0.9.0 supports MLB, NFL, NBA and NHL score rotation. NBA/NHL are off by
default for existing installations; enable them in the dashboard or remote menu.

On the remote, press Select once → Sports. Up/down chooses a sport, A or
left/right toggles it, and Save Changes applies it. B returns without saving.
The local team-calendar/record rotation has its own switch.

In the dashboard, open Scoreboard Settings → Sports & teams in rotation:

1. Enable the sports you want, or choose Only this sport next to NHL, for example.
2. Expand a sport's team settings. Choose All teams or Selected teams only.
3. Select any teams, including those with no game today, and Save Preferences.

A selected team's games include both opponents. Selecting no teams shows no
games for that sport. Favorites remain separate from the rotation filter.
Your existing league choices, team selections, brightness and night policy
survive partial settings saves and updates. Legacy NFL favorites-only choices
are preserved when a sports policy is first created.

NBA/NHL show scheduled/live/final scores, quarters or periods, provider clocks,
overtime and shootout states. They use bounded ESPN website scoreboards with
caching and clear stale/error states. Disabled leagues make no score requests.
The feeds have no verified API contract, service guarantee or published polling
allowance. No credentials were required for the tested endpoints. Official
logos are optional and not bundled. No NBA basket or NHL goal alerts are added.

Past Scores respects saved sport/team filters and returns to live after ten
minutes. Holding a card stops rotation while live updates continue. The browser
experiment is available through `npm run dev:sports` at
`http://127.0.0.1:5177/sports`; it is separate from your installed device settings.

## Recover a retained version

The staged updater retains the previous release and rolls back if the new
release fails startup verification/health checks. For a later rollback, use
`sudo bash scripts/rollback-device.sh BUILD_ID` from the checked-out source tree on the device, supplying the
retained build ID from your installation. Release directories, service paths
and administrative access must match the installation. Rollback preserves
shared durable state and selects the retained release's configuration.
The startup health check is not a promise of automatic rollback for later crashes.

Physical readability, remote response, refresh/flicker and long-running use
must be checked on your own Pi/panel. Passing source tests or browser previews
does not establish hardware acceptance.

Release validation: 316 TypeScript/component tests, 253 Python tests, production
build and whitespace checks passed from the public source tree without private
assets or configuration. Seventy new exact TS/Python sports cases are included
in package verification. Runtime test HTTP servers use ephemeral ports so
separate checkouts cannot collide during validation.
