#!/usr/bin/env bash
set -euo pipefail

# Find repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${1:-/opt/pixelboard}"
RELEASES_DIR="/opt/pixelboard/releases"
STATE_DIR="/var/lib/pixelboard"
HEALTH_TIMEOUT_SEC="${SCOREBOARD_HEALTH_TIMEOUT_SEC:-90}"
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
PREVIOUS_RELEASE=""
LEGACY_RELEASE=""
PREVIOUS_UNIT=""
ACTIVATED=0
ACTIVATED_AT=""

echo "=== Scoreboard Device Update ==="
echo "Repository: ${REPO_DIR}"
echo "Target:     ${TARGET_DIR}"

if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "Error: Target directory ${TARGET_DIR} does not exist." >&2
  exit 1
fi

install -d -o root -g root -m 0755 "${RELEASES_DIR}" "${STATE_DIR}"
CURRENT_RELEASE="$(readlink -f "${TARGET_DIR}")"
# A legacy directory kept state beside the live code. Seed the durable state
# directory before the first release-link migration without overwriting any
# state already managed by a newer release.
if [[ -d "${CURRENT_RELEASE}/state" && ! -L "${CURRENT_RELEASE}/state" ]]; then
  cp -an "${CURRENT_RELEASE}/state/." "${STATE_DIR}/"
fi
exec 9>"${STATE_DIR}/update.lock"
if ! flock -n 9; then
  echo "Error: another scoreboard update is already running." >&2
  exit 1
fi
if [[ -L "${TARGET_DIR}" ]]; then
  PREVIOUS_RELEASE="$(readlink -f "${TARGET_DIR}")"
else
  LEGACY_RELEASE="${RELEASES_DIR}/legacy-${RELEASE_ID}"
fi

rollback() {
  trap - ERR
  echo "Update failed — restoring the prior release." >&2
  # Stop and clear systemd's automatic restart loop before the staged files
  # disappear. Otherwise a child process can retry against a deleted release.
  systemctl stop scoreboard.service || true
  systemctl reset-failed scoreboard.service || true
  rm -f "${TARGET_DIR}"
  if [[ -n "${PREVIOUS_RELEASE}" && -d "${PREVIOUS_RELEASE}" ]]; then
    ln -s "${PREVIOUS_RELEASE}" "${TARGET_DIR}"
  elif [[ -n "${LEGACY_RELEASE}" && -d "${LEGACY_RELEASE}" ]]; then
    mv "${LEGACY_RELEASE}" "${TARGET_DIR}"
  fi
  if [[ -n "${PREVIOUS_UNIT}" && -f "${PREVIOUS_UNIT}" ]]; then
    install -o root -g root -m 0644 "${PREVIOUS_UNIT}" /etc/systemd/system/scoreboard.service
    systemctl daemon-reload || true
  fi
  systemctl start scoreboard.service || true
  rm -rf "${RELEASE_DIR}"
}

on_error() {
  result=$?
  if [[ "${ACTIVATED}" -eq 1 ]]; then
    rollback
  else
    if [[ -n "${PREVIOUS_UNIT}" && -f "${PREVIOUS_UNIT}" ]]; then
      install -o root -g root -m 0644 "${PREVIOUS_UNIT}" /etc/systemd/system/scoreboard.service
      systemctl daemon-reload || true
    fi
    rm -rf "${RELEASE_DIR}"
  fi
  exit "${result}"
}
trap on_error ERR

echo "[1/5] Pulling latest changes from GitHub..."
cd "${REPO_DIR}"
REPO_OWNER="$(stat -c '%U' "${REPO_DIR}" 2>/dev/null || stat -f '%Su' "${REPO_DIR}" 2>/dev/null || echo "")"
if [[ -z "${REPO_OWNER}" || "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Error: run this updater as root from a repository owned by a non-root operator." >&2
  exit 1
fi
REPO_OWNER_HOME="$(getent passwd "${REPO_OWNER}" | cut -d: -f6)"
if [[ -z "${REPO_OWNER_HOME}" || ! -d "${REPO_OWNER_HOME}" ]]; then
  echo "Error: could not resolve home directory for ${REPO_OWNER}." >&2
  exit 1
fi
# Only repair Git metadata; never take ownership of an arbitrary source tree.
chown -R "${REPO_OWNER}:${REPO_OWNER}" "${REPO_DIR}/.git"
chmod -R u+rwX "${REPO_DIR}/.git"
sudo -u "${REPO_OWNER}" env HOME="${REPO_OWNER_HOME}" GIT_TERMINAL_PROMPT=0 \
  git -c "safe.directory=${REPO_DIR}" -C "${REPO_DIR}" pull --ff-only origin main
if ! sudo -u "${REPO_OWNER}" git -C "${REPO_DIR}" diff --quiet || ! sudo -u "${REPO_OWNER}" git -C "${REPO_DIR}" diff --cached --quiet; then
  echo "Error: refusing to deploy a dirty source checkout." >&2
  exit 1
fi
SOURCE_COMMIT="$(sudo -u "${REPO_OWNER}" git -C "${REPO_DIR}" rev-parse HEAD)"

# This root-owned pointer is the sole repository location accepted by the web
# updater. It intentionally lives outside the dashboard-writable release tree.
install -d -o root -g root -m 0755 /etc/pixelboard
printf '%s\n' "${REPO_DIR}" | install -o root -g root -m 0644 /dev/stdin /etc/pixelboard/source-repo

echo "[2/5] Staging and verifying release ${RELEASE_ID}..."
install -d -o root -g root -m 0755 "${RELEASE_DIR}"
cp -a "$(readlink -f "${TARGET_DIR}")/." "${RELEASE_DIR}/"
DEFINITION_REF="$("${RELEASE_DIR}/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["displayDefinitionId"])' "${RELEASE_DIR}/config/project.json")"
DEFINITION_ID="${DEFINITION_REF%%@*}"
DEFINITION_SOURCE="${REPO_DIR}/definition/${DEFINITION_ID}"
if [[ ! -f "${DEFINITION_SOURCE}/display-definition.json" || ! -d "${DEFINITION_SOURCE}/fonts" ]]; then
  echo "Error: repository definition ${DEFINITION_ID} is incomplete." >&2
  exit 1
fi
rm -rf "${RELEASE_DIR}/runtime/scoreboard_device" "${RELEASE_DIR}/runtime/shared_py" "${RELEASE_DIR}/definition" "${RELEASE_DIR}/fixtures" "${RELEASE_DIR}/scripts"
cp -a "${REPO_DIR}/targets/linux-sbc-hub75/runtime/scoreboard_device" "${RELEASE_DIR}/runtime/scoreboard_device"
cp -a "${REPO_DIR}/shared_py" "${RELEASE_DIR}/runtime/shared_py"
install -d -o root -g root -m 0755 "${RELEASE_DIR}/definition"
cp -a "${DEFINITION_SOURCE}/." "${RELEASE_DIR}/definition/"
cp -a "${REPO_DIR}/fixtures" "${RELEASE_DIR}/fixtures"
cp -a "${REPO_DIR}/scripts" "${RELEASE_DIR}/scripts"
install -m 0644 "${REPO_DIR}/targets/linux-sbc-hub75/package/scoreboard.service" "${RELEASE_DIR}/scoreboard.service"
install -d -o root -g root -m 0750 "${RELEASE_DIR}/state" "${RELEASE_DIR}/config"
rm -rf "${RELEASE_DIR}/state"
ln -sfn "${STATE_DIR}" "${RELEASE_DIR}/state"
printf '{"buildId":"%s","sourceCommit":"%s","sourceDirty":false}\n' "${RELEASE_ID}" "${SOURCE_COMMIT}" > "${RELEASE_DIR}/release-identity.json"
PYTHONPATH="${RELEASE_DIR}/runtime" "${RELEASE_DIR}/.venv/bin/python" -m scoreboard_device --root "${RELEASE_DIR}" verify --output-dir "${STATE_DIR}/verification"

echo "[3/5] Activating verified release..."
if command -v systemctl >/dev/null 2>&1; then
  if [[ -f /etc/systemd/system/scoreboard.service ]]; then
    PREVIOUS_UNIT="${STATE_DIR}/scoreboard.service.before-${RELEASE_ID}"
    install -o root -g root -m 0600 /etc/systemd/system/scoreboard.service "${PREVIOUS_UNIT}"
  fi
  install -o root -g root -m 0644 "${RELEASE_DIR}/scoreboard.service" /etc/systemd/system/scoreboard.service
  systemctl daemon-reload
fi
ACTIVATED=1
if [[ -n "${LEGACY_RELEASE}" ]]; then mv "${TARGET_DIR}" "${LEGACY_RELEASE}"; fi
ln -s "${RELEASE_DIR}" "${TARGET_DIR}.next"
mv -Tf "${TARGET_DIR}.next" "${TARGET_DIR}"
ACTIVATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
systemctl restart scoreboard.service

echo "[4/5] Verifying device status..."
DEADLINE=$((SECONDS + HEALTH_TIMEOUT_SEC))
while [[ "${SECONDS}" -lt "${DEADLINE}" ]]; do
  if STATUS_JSON="$(curl -fsS --max-time 3 http://127.0.0.1:8123/status 2>/dev/null)" && \
      ACTUAL_BUILD_ID="$(printf '%s' "${STATUS_JSON}" | "${RELEASE_DIR}/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin).get("installedBuild", {}).get("buildId", ""))')" && \
      [[ "${ACTUAL_BUILD_ID}" == "${RELEASE_ID}" ]]; then
    rm -f "${PREVIOUS_UNIT}"
    # Dashboard mutations now share the six-digit household PIN. Retire the
    # legacy random admin token only after the new release passes its health check.
    rm -f "${STATE_DIR}/admin-token"
    trap - ERR
    echo "[5/5] Device is up and healthy: ${RELEASE_ID}"
    exit 0
  fi
  sleep 1
done

echo "Candidate service status at failed health check:" >&2
systemctl status scoreboard.service --no-pager -l >&2 || true
if [[ -n "${ACTIVATED_AT}" ]]; then
  echo "Candidate service logs since activation:" >&2
  journalctl -u scoreboard.service --since "${ACTIVATED_AT}" --no-pager -o short-precise -n 80 >&2 || true
fi
rollback
trap - ERR
echo "Error: health check timed out; prior release was restored." >&2
exit 1
