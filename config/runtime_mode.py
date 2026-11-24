"""Runtime mode: launch a local Camoufox, or attach to a browser that exists.

The proxy has two ways to reach a page:

* **standard** — `launch_camoufox.py` starts a local Camoufox child process and
  connects to the WebSocket endpoint that process prints;
* **termux** — nothing is launched. Android/Termux cannot host Camoufox (it is a
  glibc Firefox build), so the browser is supplied by the operator: a local
  Chromium/Chrome started with `--remote-debugging-port`, or Camoufox running on
  another machine and reached over the network.

Selection is explicit:

    RUNTIME_MODE=standard | termux | auto

`auto` resolves to `termux` when the Termux environment is detected and to
`standard` otherwise. Anything else (or unset) is `standard`, so behaviour never
changes because of the host it happens to run on.

Endpoint resolution, first hit wins:

    BROWSER_CDP_ENDPOINT   http://host:port   chromium.connect_over_cdp
    BROWSER_WS_ENDPOINT    ws://...           firefox.connect, or chromium.connect
                                              when BROWSER_KIND=chromium
    CAMOUFOX_WS_ENDPOINT   set by the standard launcher; honoured last

BROWSER_KIND (`firefox` / `chromium`) overrides the scheme-based guess.
"""

import os
import sys
import tempfile
from typing import Any, Dict

TERMUX_PREFIX = "/data/data/com.termux/files/usr"

_ENDPOINT_VARS = ("BROWSER_CDP_ENDPOINT", "BROWSER_WS_ENDPOINT", "CAMOUFOX_WS_ENDPOINT")

_MODES_TERMUX = {"termux", "attach", "android"}
_MODES_STANDARD = {"standard", "normal", "local", "desktop", "camoufox"}


def is_termux() -> bool:
    """Whether this process is running inside Termux, not just on Linux.

    `platform.system()` reports "Linux" on Android, so it cannot be used. The
    Termux marker, the `$PREFIX` path and the interpreter path are checked
    instead; any one is enough.
    """
    if os.environ.get("TERMUX_VERSION"):
        return True
    prefix = (os.environ.get("PREFIX") or "").rstrip("/")
    if prefix == TERMUX_PREFIX:
        return True
    return "com.termux" in (sys.executable or "")


def runtime_mode() -> str:
    """Resolved mode: "standard" or "termux"."""
    raw = (os.environ.get("RUNTIME_MODE") or "").strip().lower()
    if raw in _MODES_TERMUX:
        return "termux"
    if raw in _MODES_STANDARD:
        return "standard"
    if raw == "auto":
        return "termux" if is_termux() else "standard"
    return "standard"


def browser_endpoint() -> str:
    """Configured browser endpoint, or "" when there is none."""
    for name in _ENDPOINT_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def browser_kind(endpoint: str = "") -> str:
    """Which Playwright connector the endpoint needs: "chromium", "firefox", "none"."""
    raw = (os.environ.get("BROWSER_KIND") or "").strip().lower()
    endpoint = endpoint or browser_endpoint()
    if raw in ("chromium", "chrome", "cdp"):
        return "chromium"
    if raw in ("firefox", "camoufox", "juggler"):
        return "firefox"
    if not endpoint:
        return "none"
    if endpoint.startswith(("http://", "https://")):
        # A CDP HTTP endpoint is only served by Chromium.
        return "chromium"
    return "firefox"


def runtime_temp_dir() -> str:
    """Writable temp directory for this host.

    `tempfile.gettempdir()` honours TMPDIR and exists on Termux, but code that
    hard-codes /tmp (which is not writable there) gets the correct path here.
    """
    if is_termux():
        prefix = (os.environ.get("PREFIX") or TERMUX_PREFIX).rstrip("/")
        candidate = os.path.join(prefix, "tmp")
        if os.path.isdir(candidate):
            return candidate
    return tempfile.gettempdir()


def runtime_snapshot() -> Dict[str, Any]:
    """Dictionary for logs and `/health`; carries no secrets."""
    endpoint = browser_endpoint()
    return {
        "mode": runtime_mode(),
        "termux": is_termux(),
        "browser": {
            "kind": browser_kind(endpoint),
            "configured": bool(endpoint),
            "endpoint": endpoint,
            "external": runtime_mode() == "termux",
        },
        "tempDir": runtime_temp_dir(),
    }
