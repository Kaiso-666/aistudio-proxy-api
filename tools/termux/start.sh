#!/usr/bin/env bash
# Start the proxy on Termux, inside the proot Debian container.
#   bash tools/termux/start.sh [--active-auth-json auth_profiles/active/login.json]
#
# The browser is a Chromium inside that container (started by run-attached.sh).
# Extra arguments are forwarded to launch_camoufox.py.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DISTRO="${PROXY_DISTRO:-debian}"

if ! command -v proot-distro >/dev/null 2>&1; then
  echo "proot-distro is not installed. Run: pkg install proot-distro" >&2
  exit 2
fi
# proot-distro >=5 keeps containers under containers/<name>; older versions
# used installed-rootfs/<name>. Check both rather than one version's layout.
if [ ! -d "$PREFIX/var/lib/proot-distro/containers/$DISTRO" ] && \
   [ ! -d "$PREFIX/var/lib/proot-distro/installed-rootfs/$DISTRO" ]; then
  echo "Container '$DISTRO' is not installed. Run:" >&2
  echo "  proot-distro install $DISTRO" >&2
  echo "  proot-distro login $DISTRO -- bash $(realpath --relative-to="$HOME" "$REPO")/tools/termux/bootstrap-debian.sh" >&2
  exit 2
fi

exec proot-distro login "$DISTRO" -- bash "$REPO/tools/termux/run-attached.sh" "$@"
