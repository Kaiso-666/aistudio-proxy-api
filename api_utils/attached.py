"""Start the proxy against a browser that already exists (Termux / attach mode).

Standard mode (`launch_camoufox.py --headless`) spawns Camoufox and connects to
the endpoint it prints. That cannot work on Android/Termux: Camoufox is a glibc
Firefox build, and there is no local browser process to spawn. Attach mode
inverts the relationship — the operator runs the browser, this process only
connects:

    # on the phone (Termux), a Chromium listening on the loopback interface
    chromium --headless=new --remote-debugging-port=9222 about:blank
    python launch_camoufox.py --termux

    # or a browser on another machine
    python launch_camoufox.py --termux --browser-endpoint ws://desktop:9222/...

What this mode does *not* do: it does not make Playwright or Camoufox run on
Android. Playwright's driver is still required to talk to the browser. If that
driver cannot run on the device, move the browser to a host that can run both.

Transport: the MITM stream proxy only sees traffic from a browser configured to
use it. An external browser is not, so attach mode defaults `STREAM_PORT=0`
(the Playwright/DOM path). Pass `--stream-port N` explicitly if you have pointed
the browser's proxy at this process.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any, Tuple


def _probe_cdp(endpoint: str, timeout: float = 3.0) -> Tuple[bool, str]:
    """Ask a CDP endpoint who it is.

    `/json/version` is served by any Chromium with --remote-debugging-port. The
    probe catches the two mistakes that otherwise surface as a 30s Playwright
    timeout: wrong port, and a browser bound to 127.0.0.1 on another host.
    """
    url = endpoint.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace") or "{}")
        identity = payload.get("Browser") or payload.get("User-Agent") or ""
        return True, str(identity)
    except Exception as exc:  # connection refused, timeout, HTML error page
        return False, str(exc)


def _stream_port_was_explicit(argv: list) -> bool:
    return any(
        arg == "--stream-port" or arg.startswith("--stream-port=") for arg in argv
    )


def run_attached(args: Any, logger: Any) -> int:
    """Configure the process and run uvicorn. Returns a process exit code."""
    from config.runtime_mode import browser_endpoint, browser_kind

    endpoint = (getattr(args, "browser_endpoint", None) or "").strip()
    if endpoint:
        # --browser-endpoint wins, and is exported so the server sees it too.
        var = (
            "BROWSER_CDP_ENDPOINT"
            if endpoint.startswith(("http://", "https://"))
            else "BROWSER_WS_ENDPOINT"
        )
        os.environ[var] = endpoint
    else:
        endpoint = browser_endpoint()

    if not endpoint:
        logger.error("")
        logger.error("❌ Attach mode has no browser to attach to.")
        logger.error(
            "   Start a browser with a debugging port and point the proxy at it:"
        )
        logger.error(
            "     chromium --headless=new --remote-debugging-port=9222 about:blank"
        )
        logger.error(
            "     python launch_camoufox.py --termux --browser-endpoint http://127.0.0.1:9222"
        )
        logger.error(
            "   Or set BROWSER_CDP_ENDPOINT / BROWSER_WS_ENDPOINT in .env."
        )
        return 2

    kind = browser_kind(endpoint)
    identity = ""
    if kind == "chromium" and not endpoint.startswith(("ws://", "wss://")):
        ok, detail = _probe_cdp(endpoint)
        if ok:
            identity = detail
        else:
            skip = (os.environ.get("BROWSER_SKIP_PROBE") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not skip:
                logger.error("")
                logger.error(f"❌ No Chromium DevTools endpoint at {endpoint}")
                logger.error(f"   ({detail})")
                logger.error(
                    "   Start it with --remote-debugging-port and bind 0.0.0.0 to "
                    "reach it from another host:"
                )
                logger.error(
                    "     chromium --headless=new --remote-debugging-address=0.0.0.0 "
                    "--remote-debugging-port=9222 about:blank"
                )
                logger.error(
                    "   Set BROWSER_SKIP_PROBE=1 to start anyway and attach later."
                )
                return 2
            logger.warning(
                f"[Attach] {endpoint} did not answer /json/version ({detail}); "
                "starting anyway (BROWSER_SKIP_PROBE=1)."
            )

    os.environ["RUNTIME_MODE"] = "termux"
    os.environ["LAUNCH_MODE"] = "attach"
    os.environ["SERVER_PORT_INFO"] = str(args.server_port)

    explicit_stream = _stream_port_was_explicit(sys.argv)
    if explicit_stream:
        os.environ["STREAM_PORT"] = str(args.stream_port)
    else:
        # An external browser does not route its traffic through this process,
        # so the aux-stream reader would wait on a queue nobody feeds.
        os.environ["STREAM_PORT"] = "0"

    if getattr(args, "active_auth_json", None):
        os.environ["ACTIVE_AUTH_JSON_PATH"] = args.active_auth_json

    logger.info("=================================================")
    logger.info("📱 Termux / attach mode")
    logger.info(f"   browser : {kind} at {endpoint}")
    if identity:
        logger.info(f"   version : {identity}")
    if explicit_stream and args.stream_port:
        logger.info(
            f"   stream  : MITM on port {args.stream_port} (the browser must use "
            "it as its proxy for the fast path)"
        )
    else:
        logger.info(
            "   stream  : DOM transport (STREAM_PORT=0). The aux stream needs a "
            "browser routed through this proxy; pass --stream-port to enable it."
        )
    logger.info(f"   api     : http://0.0.0.0:{args.server_port}/v1")
    logger.info("=================================================")

    import uvicorn  # local import: keeps --help and the error paths light

    from server import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.server_port,
        log_config=None,
        access_log=False,
    )
    return 0
