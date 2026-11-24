#!/usr/bin/env bash
# Bootstrap the proxy inside a proot Debian container on Termux.
# Run as:  proot-distro login debian -- bash <repo>/tools/termux/bootstrap-debian.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
REPO="${PROXY_REPO:-/data/data/com.termux/files/home/aistudio-proxy-api}"
VENV="${PROXY_VENV:-/opt/proxy-venv}"

# IPv6 is not routed inside proot here; without this apt resolves to IPv6 and
# fails with "Temporary failure resolving deb.debian.org" after printing an
# IPv4 address.
APT_OPTS=(-o Acquire::ForceIPv4=true)

apt-get "${APT_OPTS[@]}" update -qq
apt-get "${APT_OPTS[@]}" install -y -qq \
  python3 python3-venv python3-pip chromium ca-certificates curl

"$(command -v python3)" -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$REPO/requirements.txt"

# No `playwright install`: attach mode connects to a browser that already
# exists, so Playwright's bundled browsers are dead weight here.
"$VENV/bin/python" - <<'PY'
import fastapi, playwright, pydantic, sys
print(f"python {sys.version.split()[0]}  fastapi {fastapi.__version__}  "
      f"pydantic {pydantic.VERSION}  playwright ok")
PY
