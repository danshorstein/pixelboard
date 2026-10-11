#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_LINK="/opt/pixelboard"
RELEASES_DIR="/opt/pixelboard/releases"
STATE_DIR="/var/lib/pixelboard"
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
HEALTH_URL="http://127.0.0.1:8123/status"
HEALTH_TIMEOUT_SEC=30
DRIVER_COMMIT="e947417fff9042b3ea173542be09490acab069f7"
DRIVER_ARCHIVE="${RELEASE_DIR}/vendor/rpi-rgb-led-matrix-${DRIVER_COMMIT}-source.tar.gz"
DRIVER_ARCHIVE_SHA256="a7862de04d63d501e734c1fe5f95ae3714903b40241d087680625b64147c11fa"
DRIVER_EXTRACTED="${RELEASE_DIR}/vendor/rpi-rgb-led-matrix-${DRIVER_COMMIT}"
DRIVER_DIR="${DRIVER_EXTRACTED}"

PREVIOUS_RELEASE=""
if [[ -L "${INSTALL_LINK}" ]]; then
  PREVIOUS_RELEASE="$(readlink -f "${INSTALL_LINK}")"
fi
SERVICE_WAS_ACTIVE=0
if systemctl is-active --quiet scoreboard.service 2>/dev/null; then
  SERVICE_WAS_ACTIVE=1
fi

rollback() {
  # Step 7 has already pointed the service at the new (bad) release and
  # started or restarted it regardless of SERVICE_WAS_ACTIVE — so recovery
  # must act unconditionally here, not only when the service was previously
  # running.
  echo "Update failed — rolling back." >&2
  if [[ -n "${PREVIOUS_RELEASE}" && -d "${PREVIOUS_RELEASE}" ]]; then
    ln -sfn "${PREVIOUS_RELEASE}" "${INSTALL_LINK}"
    systemctl restart scoreboard.service || true
    echo "Rolled back to the previous known-good release: ${PREVIOUS_RELEASE}" >&2
  else
    # No known-good release to fall back to (first-time install). Stop the
    # service rather than leave it crash-looping against a release we are
    # about to delete.
    systemctl stop scoreboard.service || true
    systemctl disable scoreboard.service || true
    rm -f "${INSTALL_LINK}"
    echo "No previous release to roll back to — stopped the service; nothing is installed." >&2
  fi
  rm -rf "${RELEASE_DIR}"
}

echo "[1/8] Installing OS prerequisites"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential cmake cython3 ninja-build \
  python3 python3-gpiozero python3-pil python3-venv python-dev-is-python3 curl

echo "[2/8] Staging the new release (the currently running installation is untouched until verified)"
install -d -m 0755 "${RELEASES_DIR}" "${STATE_DIR}" "${RELEASE_DIR}"
cp -a "${SOURCE_DIR}/." "${RELEASE_DIR}/"
# State (diagnostics, verification output) persists across releases instead
# of resetting on every install/upgrade — every release shares one directory.
rm -rf "${RELEASE_DIR}/state"
ln -sfn "${STATE_DIR}" "${RELEASE_DIR}/state"

echo "[3/8] Creating the isolated Python environment"
python3 -m venv --system-site-packages "${RELEASE_DIR}/.venv"
"${RELEASE_DIR}/.venv/bin/pip" install --disable-pip-version-check -r "${RELEASE_DIR}/runtime/requirements.lock.txt"

echo "[4/8] Verifying the packaged HUB75 driver source"
if [[ ! -f "${DRIVER_ARCHIVE}" ]]; then
  echo "Missing packaged driver source: ${DRIVER_ARCHIVE}" >&2
  rm -rf "${RELEASE_DIR}"
  exit 1
fi
if ! echo "${DRIVER_ARCHIVE_SHA256}  ${DRIVER_ARCHIVE}" | sha256sum --check --status; then
  echo "Packaged driver source failed checksum verification." >&2
  rm -rf "${RELEASE_DIR}"
  exit 1
fi
if [[ ! -d "${DRIVER_EXTRACTED}" ]]; then
  tar -xzf "${DRIVER_ARCHIVE}" -C "${RELEASE_DIR}/vendor"
fi

echo "[5/8] Building the pinned Python matrix binding"
"${RELEASE_DIR}/.venv/bin/pip" install \
  --disable-pip-version-check --no-build-isolation --no-deps "${DRIVER_DIR}"

echo "[6/8] Running artifact verification against the staged release (not yet live)"
if ! PYTHONPATH="${RELEASE_DIR}/runtime" "${RELEASE_DIR}/.venv/bin/python" \
  -m scoreboard_device --root "${RELEASE_DIR}" verify --output-dir "${STATE_DIR}/verification"; then
  echo "Staged release failed verification before going live." >&2
  rm -rf "${RELEASE_DIR}"
  exit 1
fi

EXPECTED_PROJECT_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RELEASE_DIR}/config/project.json")"
EXPECTED_PROJECT_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["meta"]["version"])' "${RELEASE_DIR}/config/project.json")"
EXPECTED_BUILD_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["buildId"])' "${RELEASE_DIR}/manifest.json")"

echo "[7/8] Swapping in the verified release and restarting the service"
ln -sfn "${RELEASE_DIR}" "${INSTALL_LINK}"
install -m 0644 "${INSTALL_LINK}/scoreboard.service" /etc/systemd/system/scoreboard.service
systemctl daemon-reload
if [[ "${SERVICE_WAS_ACTIVE}" -eq 1 ]]; then
  # The service is already running an older release — `enable --now` would be
  # a no-op against an already-active unit and would silently keep serving
  # the old code. Restart explicitly so the new release actually takes over.
  systemctl restart scoreboard.service
else
  systemctl enable --now scoreboard.service
fi

echo "[8/8] Confirming the new release's identity is actually serving"
DEADLINE=$((SECONDS + HEALTH_TIMEOUT_SEC))
HEALTHY=0
while [[ "${SECONDS}" -lt "${DEADLINE}" ]]; do
  if STATUS_JSON="$(curl -fsS --max-time 3 "${HEALTH_URL}" 2>/dev/null)"; then
    ACTUAL_ID="$(printf '%s' "${STATUS_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["project"]["id"])' 2>/dev/null || true)"
    ACTUAL_VERSION="$(printf '%s' "${STATUS_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["project"]["version"])' 2>/dev/null || true)"
    ACTUAL_BUILD_ID="$(printf '%s' "${STATUS_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("installedBuild", {}).get("buildId", ""))' 2>/dev/null || true)"
    ACTUAL_FRAMES="$(printf '%s' "${STATUS_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("render", {}).get("frames", 0))' 2>/dev/null || true)"
    if [[ "${ACTUAL_ID}" == "${EXPECTED_PROJECT_ID}" && "${ACTUAL_VERSION}" == "${EXPECTED_PROJECT_VERSION}" && "${ACTUAL_BUILD_ID}" == "${EXPECTED_BUILD_ID}" && "${ACTUAL_FRAMES}" =~ ^[1-9][0-9]*$ ]]; then
      HEALTHY=1
      break
    fi
  fi
  sleep 1
done

if [[ "${HEALTHY}" -ne 1 ]]; then
  rollback
  exit 1
fi

# Verified healthy on the new release — safe to drop the old one. Only the
# immediately prior release is kept as the known-good rollback target, so an
# operator always has exactly one verified fallback, not an unbounded history.
if [[ -n "${PREVIOUS_RELEASE}" && "${PREVIOUS_RELEASE}" != "${RELEASE_DIR}" ]]; then
  for candidate in "${RELEASES_DIR}"/*; do
    [[ -d "${candidate}" ]] || continue
    if [[ "${candidate}" != "${RELEASE_DIR}" && "${candidate}" != "${PREVIOUS_RELEASE}" ]]; then
      rm -rf "${candidate}"
    fi
  done
fi

echo
echo "Installed release ${RELEASE_ID}. Check: systemctl status scoreboard.service"
echo "Device status: http://$(hostname -I | awk '{print $1}'):8123/status"
if [[ -n "${PREVIOUS_RELEASE}" ]]; then
  echo "Previous known-good release kept for rollback: ${PREVIOUS_RELEASE}"
fi
