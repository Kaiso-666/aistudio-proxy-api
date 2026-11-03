#!/usr/bin/env python3
"""
verify_stealth.py - prove the anti-detection changes actually work.

Two things are checked against a real Camoufox build, with no Google account
and no network dependency:

  1. Prompt entry. A textarea is instrumented to record every keydown /
     beforeinput / input / change / composition event. The module under test
     must reproduce the *event shape* a human produces, not just the final
     string.

  2. Fingerprint surface. Probes that any bot-detection script can run in
     three lines: navigator.webdriver, innerWidth vs outerWidth coherence,
     timezone, WebGL vendor, plugin/mime counts, canvas determinism.

Run:  .venv\\Scripts\\python.exe tools\\verify_stealth.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.async_api import AsyncCamoufox  # noqa: E402

from browser_utils.human_input import insert_prompt_text  # noqa: E402

INSTRUMENTED_PAGE = """
<!doctype html>
<html><body>
<textarea id="prompt" aria-label="Enter a prompt"></textarea>
<pre id="log" style="display:none"></pre>
<script>
// Log through the DOM, not through a JS global: Playwright's Firefox
// evaluates in a sandbox that shares the document but not window expandos,
// so `window.__events` would read back as undefined.
const ta = document.getElementById('prompt');
const sink = document.getElementById('log');
const rec = (type, extra) => {
  sink.textContent += JSON.stringify(Object.assign({t: type}, extra || {})) + '\\n';
};

ta.addEventListener('keydown',      e => rec('keydown',  {key: e.key}));
ta.addEventListener('keyup',        e => rec('keyup',    {key: e.key}));
ta.addEventListener('beforeinput',  e => rec('beforeinput', {inputType: e.inputType}));
ta.addEventListener('input',        e => rec('input',    {inputType: e.inputType}));
ta.addEventListener('change',       () => rec('change'));
ta.addEventListener('paste',        () => rec('paste'));
ta.addEventListener('compositionstart', () => rec('compositionstart'));
</script>
</body></html>
"""

PROBES = """
() => {
  const gl = document.createElement('canvas').getContext('webgl');
  const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return {
    webdriver: navigator.webdriver,
    innerWidth: window.innerWidth,
    outerWidth: window.outerWidth,
    innerHeight: window.innerHeight,
    outerHeight: window.outerHeight,
    widthDelta: window.outerWidth - window.innerWidth,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    languages: navigator.languages,
    platform: navigator.platform,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory,
    plugins: navigator.plugins.length,
    mimeTypes: navigator.mimeTypes.length,
    webglVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
    webglRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
    screen: [screen.width, screen.height],
    colorDepth: screen.colorDepth,
    hasChrome: typeof window.chrome !== 'undefined',
    connection: navigator.connection ? navigator.connection.effectiveType : null,
  };
}
"""

CANVAS_HASH = """
() => {
  const c = document.createElement('canvas');
  c.width = 200; c.height = 40;
  const x = c.getContext('2d');
  x.textBaseline = 'top';
  x.font = '14px Arial';
  x.fillStyle = '#f60';
  x.fillRect(125, 1, 62, 20);
  x.fillStyle = '#069';
  x.fillText('fingerprint', 2, 15);
  return c.toDataURL().slice(-64);
}
"""


async def probe_fingerprint(browser) -> dict:
    page = await browser.new_page()
    await page.set_content("<!doctype html><html><body></body></html>")
    values = await page.evaluate(PROBES)
    hashes = {await page.evaluate(CANVAS_HASH) for _ in range(3)}
    values["canvasVariantsAcrossReads"] = len(hashes)
    await page.close()
    return values


async def probe_input(browser, text: str, label: str) -> dict:
    page = await browser.new_page()
    await page.set_content(INSTRUMENTED_PAGE)
    locator = page.locator("#prompt")

    ok = await insert_prompt_text(page, locator, text)

    events = await page.evaluate(
        "() => document.getElementById('log').textContent"
    )
    events = [json.loads(line) for line in (events or "").splitlines() if line.strip()]
    value = await page.evaluate("() => document.getElementById('prompt').value")
    await page.close()

    kinds: dict[str, int] = {}
    input_types: dict[str, int] = {}
    for ev in events:
        kinds[ev["t"]] = kinds.get(ev["t"], 0) + 1
        if ev["t"] in ("input", "beforeinput"):
            input_types[str(ev.get("inputType"))] = (
                input_types.get(str(ev.get("inputType")), 0) + 1
            )

    return {
        "label": label,
        "chars": len(text),
        "verified": ok,
        "valueMatches": value == text,
        "eventKinds": kinds,
        "inputTypes": input_types,
        "totalEvents": len(events),
    }


def report(title: str, payload) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


async def main() -> int:
    from tzlocal import get_localzone_name
    from camoufox.fingerprints import Screen

    launch_kwargs = {
        "headless": True,
        "humanize": True,
        "locale": "en-US",
        # Constrain the preset to the host OS, exactly as the launcher does.
        # Without this the generator is free to claim Linux on a Windows box.
        "os": "windows",
        "fingerprint_preset": True,
        "canvas_noise": True,
        # No explicit window: let Camoufox size it to the generated screen.
        # A forced 1440x900 window can exceed a generated 1280x672 screen,
        # producing outerHeight > screen.height, which is impossible.
        "screen": Screen(min_width=1536, min_height=864),
        # Same deliberate pin the launcher applies: stop the preset from
        # reporting a timezone unrelated to the host/IP.
        "config": {"timezone": get_localzone_name()},
        "firefox_user_prefs": {"dom.webdriver.enabled": False},
    }

    async with AsyncCamoufox(**launch_kwargs) as browser:
        fp = await probe_fingerprint(browser)
        report("fingerprint", fp)

        short = await probe_input(browser, "Explain CRDTs in two sentences.", "short -> typing")
        report("short prompt", short)

        long_text = "Summarise this log:\n" + ("line of diagnostics; " * 120)
        long_res = await probe_input(browser, long_text, "long -> paste/IME primitive")
        report("long prompt", long_res)

    problems = []
    if fp["webdriver"] is not False:
        problems.append(f"navigator.webdriver == {fp['webdriver']!r}")
    if abs(fp["widthDelta"]) > 40:
        problems.append(
            f"innerWidth/outerWidth incoherent (delta {fp['widthDelta']}px)"
        )
    if fp["outerWidth"] > fp["screen"][0] or fp["outerHeight"] > fp["screen"][1]:
        problems.append(
            f"window larger than screen ({fp['outerWidth']}x{fp['outerHeight']} "
            f"on {fp['screen'][0]}x{fp['screen'][1]})"
        )
    if short["eventKinds"].get("keydown", 0) < short["chars"]:
        problems.append("short prompt produced no per-character keydown events")
    if not short["valueMatches"]:
        problems.append("short prompt did not verify")
    if not long_res["valueMatches"]:
        problems.append("long prompt did not verify")
    if long_res["eventKinds"].get("keydown", 0) > 5:
        problems.append("long prompt spanwed per-character key events (implausible)")

    report("verdict", {"problems": problems, "pass": not problems})
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
