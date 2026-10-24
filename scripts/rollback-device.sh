#!/usr/bin/env bash
# Restore a retained, verified release. Does not reset durable household state.
set -euo pipefail
RELEASES_DIR=/opt/pixelboard/releases
TARGET_DIR=/opt/pixelboard
if [[ ${EUID:-$(id -u)} -ne 0 || $# -ne 1 || ! "$1" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]]; then
  echo 'Usage: sudo bash rollback-device.sh BUILD_ID' >&2; exit 2
fi
CANDIDATE="${RELEASES_DIR}/$1"
if [[ ! -d "$CANDIDATE" || -L "$CANDIDATE" || ! -f "$CANDIDATE/release-identity.json" || ! -f "$CANDIDATE/scoreboard.service" ]]; then
  echo 'Retained release is missing or invalid.' >&2; exit 1
fi
if [[ $(stat -c %u "$CANDIDATE") != 0 || -n $(find "$CANDIDATE" -maxdepth 0 -perm /022 -print) ]]; then
  echo 'Refusing an untrusted release directory.' >&2; exit 1
fi
exec 9>/var/lib/pixelboard/update.lock
flock -n 9 || { echo 'An update is already running.' >&2; exit 1; }
PREVIOUS=$(readlink -f "$TARGET_DIR")
systemctl stop scoreboard.service
LINK="${TARGET_DIR}.rollback-$$"
ln -s "$CANDIDATE" "$LINK"
mv -Tf "$LINK" "$TARGET_DIR"
install -o root -g root -m 0644 "$CANDIDATE/scoreboard.service" /etc/systemd/system/scoreboard.service
systemctl daemon-reload
systemctl reset-failed scoreboard.service
systemctl start scoreboard.service
for attempt in $(seq 1 90); do
  if curl --max-time 2 -fsS http://127.0.0.1:8123/status | "$CANDIDATE/.venv/bin/python" -c 'import json,sys; s=json.load(sys.stdin); sys.exit(0 if s.get("installedBuild",{}).get("buildId")==sys.argv[1] else 1)' "$1"; then
    echo "Restored retained build $1; previous path: $PREVIOUS"; exit 0
  fi
  sleep 1
done
echo 'Rollback service did not pass its health check; inspect systemctl status scoreboard.service.' >&2
exit 1
