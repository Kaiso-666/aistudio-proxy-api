#!/usr/bin/env bash
# Run the proxy inside the proot Debian container, attached to a local Chromium.
# Called by tools/termux/start.sh; can also be run directly from inside proot.
set -euo pipefail

REPO="${PROXY_REPO:-/data/data/com.termux/files/home/aistudio-proxy-api}"
VENV="${PROXY_VENV:-/opt/proxy-venv}"
CDP_PORT="${CDP_PORT:-9222}"
PROXY_PORT="${PROXY_PORT:-2048}"

started_chromium=0
cleanup() {
  if [ "$started_chromium" = "1" ]; then
    pkill -f "remote-debugging-port=${CDP_PORT}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if ! curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "[termux] starting chromium on ${CDP_PORT}"
  # --no-sandbox: the container runs as root; --disable-dev-shm-usage: proot's
  # /dev/shm is small enough that Chromium crashes without it.
  chromium --headless=new --no-sandbox --disable-dev-shm-usage \
    --remote-debugging-address=127.0.0.1 --remote-debugging-port="${CDP_PORT}" \
    about:blank >/tmp/chromium.log 2>&1 &
  started_chromium=1
  for _ in $(seq 1 30); do
    sleep 1
    if curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
      break
    fi
  done
  if ! curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
    echo "[termux] chromium did not open a CDP port; see /tmp/chromium.log" >&2
    tail -20 /tmp/chromium.log >&2 || true
    exit 2
  fi
fi

exec "$VENV/bin/python" "$REPO/launch_camoufox.py" \
  --termux \
  --browser-endpoint "http://127.0.0.1:${CDP_PORT}" \
  --server-port "$PROXY_PORT" \
  "$@"
