#!/usr/bin/env bash
# One-time Google sign-in on the device itself, then save the session.
#
# Run it from an interactive Termux shell (it needs a TTY to wait for you):
#   bash tools/termux/login-on-device.sh
#
# It starts a virtual X display, a visible Chromium on it, and a VNC server on
# 127.0.0.1:5900. Connect a VNC viewer app to that address, sign in to Google,
# then press Enter in this terminal. The proxy stores the resulting cookies in
# auth_profiles/active/ so later headless runs do not need any of this.
set -euo pipefail

REPO="${PROXY_REPO:-/data/data/com.termux/files/home/aistudio-proxy-api}"
VENV="${PROXY_VENV:-/opt/proxy-venv}"
DISPLAY_NUM="${DISPLAY_NUM:-:99}"
VNC_PORT="${VNC_PORT:-5900}"
CDP_PORT="${CDP_PORT:-9222}"
PROXY_PORT="${PROXY_PORT:-2048}"
SAVE_AS="${SAVE_AS:-login}"

cleanup() {
  pkill -f "remote-debugging-port=${CDP_PORT}" 2>/dev/null || true
  pkill -f "x11vnc -display ${DISPLAY_NUM}" 2>/dev/null || true
  pkill -f "Xvfb ${DISPLAY_NUM}" 2>/dev/null || true
}
trap cleanup EXIT

echo "[login] starting Xvfb on ${DISPLAY_NUM}"
Xvfb "${DISPLAY_NUM}" -screen 0 1280x900x24 >/tmp/xvfb.log 2>&1 &
sleep 2

echo "[login] starting Chromium on ${DISPLAY_NUM} (CDP ${CDP_PORT})"
DISPLAY="${DISPLAY_NUM}" chromium --no-sandbox --disable-dev-shm-usage \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="${CDP_PORT}" \
  --no-first-run --no-default-browser-check \
  --user-data-dir=/tmp/chromium-login-profile \
  about:blank >/tmp/chromium-login.log 2>&1 &

for _ in $(seq 1 30); do
  sleep 1
  if curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
    break
  fi
done
if ! curl -sf "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "[login] Chromium did not start; see /tmp/chromium-login.log" >&2
  exit 2
fi

echo "[login] starting x11vnc on 127.0.0.1:${VNC_PORT} (no password: loopback only)"
x11vnc -display "${DISPLAY_NUM}" -localhost -rfbport "${VNC_PORT}" -nopw -forever -shared \
  >/tmp/x11vnc.log 2>&1 &
sleep 2

cat <<'MSG'

  Connect a VNC viewer to  127.0.0.1:5900
  (works from Termux: pkg install tigervnc  ->  vncviewer 127.0.0.1:5900,
   or any VNC app on another device over an SSH tunnel).

  In that window: sign in to Google in the AI Studio window (the proxy opens
  its own tab in this browser), make sure the prompt box is visible, then come
  back here and press Enter. The cookies are saved to
  auth_profiles/saved/<name>.json for later headless runs.

MSG

# The proxy's attach mode prompts for exactly this and saves the session when
# AUTO_SAVE_AUTH is on. It creates its own context, so the login happens in the
# context whose cookies are then written to auth_profiles/active/.
AUTO_SAVE_AUTH=true SAVE_AUTH_FILENAME="${SAVE_AS}" \
  exec "$VENV/bin/python" "$REPO/launch_camoufox.py" \
    --termux \
    --browser-endpoint "http://127.0.0.1:${CDP_PORT}" \
    --server-port "${PROXY_PORT}"
