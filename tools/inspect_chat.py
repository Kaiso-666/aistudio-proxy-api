#!/usr/bin/env python3
"""
inspect_chat.py - drive one AI Studio turn manually and dump what the DOM does.

Used to reverse the current UI after an upstream change: submit a prompt, then
report which response containers exist, so the proxy's selectors can be fixed
against observation instead of guesswork.

Usage:
    python tools/inspect_chat.py [--prompt "..."] [--wait 15]
"""

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from camoufox.async_api import AsyncCamoufox  # noqa: E402

PROMPT_SELECTOR = (
    "textarea.textarea, ms-autosize-textarea textarea, ms-chunk-input textarea, "
    "ms-prompt-input-wrapper textarea, ms-prompt-box textarea"
)
RUN_SELECTOR = "ms-run-button button.ms-button-primary, ms-run-button button"

INTERESTING = [
    "ms-chat-turn",
    "ms-prompt-scrollbar",
    "ms-response-container",
    "model-response",
    "ms-chunk-editor",
    "ms-run-button",
    "ms-stop-button",
    "ms-prompt-renderer",
    "ms-markdown",
    "ms-cmark-node",
    "ms-code-block",
    "ms-thinking-indicator",
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="Reply with exactly: PROXY_OK")
    ap.add_argument("--wait", type=int, default=15)
    ap.add_argument("--mode", choices=["plain", "human"], default="plain")
    ap.add_argument(
        "--auth",
        default=str(ROOT / "auth_profiles" / "active" / "login.json"),
    )
    args = ap.parse_args()

    out_png = Path(r"C:\Users\meow\AppData\Local\Temp\opencode\inspect.png")
    out_html = Path(r"C:\Users\meow\AppData\Local\Temp\opencode\inspect.html")

    async with AsyncCamoufox(headless=True, locale="en-US", os="windows") as browser:
        context = await browser.new_context(storage_state=args.auth)
        page = await context.new_page()
        await page.goto(
            "https://aistudio.google.com/prompts/new_chat",
            wait_until="domcontentloaded",
            timeout=120000,
        )
        await page.wait_for_selector(PROMPT_SELECTOR, timeout=60000)

        # Close the upsell dialog if present.
        btn = page.locator("ms-upgrade-options-dialog button[aria-label='close']").first
        if await btn.count() and await btn.is_visible():
            await btn.click(timeout=3000)
            print("dialog: dismissed")
        else:
            print("dialog: not present")

        editor = page.locator(PROMPT_SELECTOR).first

        if args.mode == "human":
            from browser_utils.human_input import insert_prompt_text
            from browser_utils.overlays import dismiss_blocking_dialogs

            await dismiss_blocking_dialogs(page)
            ok = await insert_prompt_text(page, editor, args.prompt)
            print("insert_prompt_text verified:", ok)
        else:
            await editor.click(timeout=10000)
            await page.keyboard.type(args.prompt, delay=0)

        run = page.locator(RUN_SELECTOR).first
        print("run button count:", await page.locator(RUN_SELECTOR).count())
        print("run enabled:", await run.is_enabled())
        await run.click(timeout=5000)
        print("clicked run")

        await asyncio.sleep(args.wait)

        html = await page.content()
        out_html.write_text(html, encoding="utf-8")
        await page.screenshot(path=str(out_png))

        print("\nurl:", page.url)
        tags = Counter(re.findall(r"<(ms-[a-z0-9-]+)", html))
        print("\ncustom elements after submit:")
        for tag in INTERESTING:
            print(f"  {tag:26s} {tags.get(tag, 0)}")

        stop = page.locator("button[aria-label*='Stop' i]")
        print("\nstop button count:", await stop.count())

        body = await page.locator("body").inner_text()
        body = re.sub(r"\n{3,}", "\n\n", body)
        print("\n--- visible text (first 1200 chars) ---")
        print(body[:1200])

        print(f"\nartifacts: {out_png} , {out_html}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
