#!/usr/bin/env python3
"""
login_capture.py - interactive one-time Google login, saved as a replayable
storage state for headless runs.

The upstream debug flow gates on `input()` (press Enter after logging in),
which cannot work from a background process. This opens the same hardened
browser, watches for the AI Studio prompt UI, and writes
`auth_profiles/active/<name>.json` the moment the session is usable.

Usage:
    python tools/login_capture.py [--timeout 600] [--out auth_profiles/active/login.json]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from camoufox.async_api import AsyncCamoufox  # noqa: E402
from camoufox.fingerprints import Screen  # noqa: E402

PROMPT_SELECTOR = (
    "textarea.textarea, "
    "ms-autosize-textarea textarea, "
    "ms-chunk-input textarea, "
    "ms-prompt-input-wrapper textarea, "
    "ms-prompt-box textarea"
)

AI_STUDIO = "aistudio.google.com"


def stealth_kwargs() -> dict:
    """Same coherence rules as launch_camoufox.build_stealth_launch_config."""
    kwargs = {
        "headless": False,
        "humanize": True,
        "locale": "en-US",
        "os": "windows",
        "fingerprint_preset": True,
        "canvas_noise": True,
        "screen": Screen(min_width=1536, min_height=864),
        "firefox_user_prefs": {
            "dom.webdriver.enabled": False,
            "media.peerconnection.ice.no_host": True,
            "media.peerconnection.ice.default_address_only": True,
        },
    }

    try:
        from camoufox.geolocation import get_geolocation
        from camoufox.ip import public_ip

        ip = public_ip()
        geo = get_geolocation(ip)
        kwargs["geoip"] = True
        kwargs["config"] = {"timezone": geo.timezone}
        print(f"[login] geoip {ip} -> {geo.timezone}", flush=True)
    except Exception as exc:
        try:
            from tzlocal import get_localzone_name

            kwargs["config"] = {"timezone": get_localzone_name()}
            print(f"[login] geoip unavailable ({exc}); host tz", flush=True)
        except Exception:
            print(f"[login] no timezone binding ({exc})", flush=True)

    return kwargs


async def wait_for_login(page, timeout_s: int) -> bool:
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        try:
            url = page.url
        except Exception:
            return False

        if url != last:
            print(f"[login] url: {url}", flush=True)
            last = url

        signed_in = AI_STUDIO in url and "accounts.google.com" not in url
        if signed_in:
            try:
                await page.wait_for_selector(PROMPT_SELECTOR, timeout=15000)
                # Let the app finish hydrating before snapshotting the session.
                await asyncio.sleep(3)
                return True
            except Exception:
                pass  # still loading, keep polling

        await asyncio.sleep(2)

    return False


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--out", default=str(ROOT / "auth_profiles" / "active" / "login.json")
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        "[login] opening browser - sign in to Google and wait for AI Studio "
        "to load. The session saves itself.",
        flush=True,
    )

    async with AsyncCamoufox(**stealth_kwargs()) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(
            f"https://{AI_STUDIO}/prompts/new_chat",
            wait_until="domcontentloaded",
            timeout=120000,
        )

        if not await wait_for_login(page, args.timeout):
            print("[login] FAILED: no authenticated AI Studio session", flush=True)
            return 1

        await context.storage_state(path=str(out_path))
        size = out_path.stat().st_size
        print(f"[login] captured {size} bytes -> {out_path}", flush=True)
        print("LOGIN_CAPTURED", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
