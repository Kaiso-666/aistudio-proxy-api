# --- browser_utils/human_input.py ---
"""
Human-plausible prompt entry for AI Studio's prompt textarea.

Why this module exists
----------------------
The original code injected the prompt with a single JavaScript assignment:

    element.value = text;
    element.dispatchEvent(new Event('input',  {bubbles: true}));
    element.dispatchEvent(new Event('change', {bubbles: true}));

That leaves a fingerprint which any behavioural collector can read in one
line of instrumentation:

  * zero ``keydown`` / ``beforeinput`` / ``keyup`` records for the turn,
  * no caret movement, no selection, no composition events,
  * ``input`` fires exactly once, with ``inputType`` undefined,
  * the entire prompt materialises inside a single event-loop turn.

It also fights the application: a raw ``value`` write updates the DOM but not
the editor's internal model, so the visible text and the submitted text can
disagree on UI revisions that track their own state.

This module writes the same text through realistic paths and *verifies* the
result, so a failure degrades instead of silently corrupting the request.

Strategy
--------
1. ``<= HUMAN_TYPE_MAX_CHARS``  -> real per-character key events.
   With Camoufox ``humanize`` enabled the browser itself supplies the cadence,
   including corrections; otherwise a small randomised delay is used.
2. longer text                 -> ``keyboard.insert_text``, which is the same
   primitive a paste/IME commit uses (one ``beforeinput`` with
   ``inputType: insertText``). A human pasting a 20 KB prompt produces this
   shape, not 20 000 keystrokes, so this is the *correct* long-text pattern
   rather than a shortcut.
3. final fallback              -> the legacy assignment, kept only so the proxy
   keeps working on editor revisions we have not seen yet.

Every path is verified by reading the field back. Nothing here raises on a
soft failure; callers get a bool and can decide.
"""

import asyncio
import os
import random
from typing import Optional

_LEGACY_FILL_JS = """
(el, text) => {
    el.value = text;
    el.dispatchEvent(new Event('input',  { bubbles: true, cancelable: true }));
    el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return el.value;
}
"""

_READ_VALUE_JS = """
(el) => (el.value !== undefined
        ? el.value
        : (el.innerText || el.textContent || ''))
"""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _normalise(value: Optional[str]) -> str:
    """Compare text the way a textarea actually stores it (CRLF -> LF)."""
    if not value:
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n")


async def _read_field(locator) -> str:
    try:
        return _normalise(await locator.evaluate(_READ_VALUE_JS, timeout=2000))
    except Exception:
        return ""


async def _focus(locator, log) -> None:
    """Click the field so the caret is real and focus events fire in order."""
    try:
        await locator.click(timeout=5000)
    except Exception as exc:  # overlay / tooltip in the way
        log(f"[HumanInput] click-to-focus failed ({exc}); using focus()")
        try:
            await locator.focus(timeout=2000)
        except Exception:
            pass


async def _clear(page, locator, log) -> None:
    """Empty the field with real editing commands, not a value reset."""
    try:
        await page.keyboard.press("ControlOrMeta+a")
        await page.keyboard.press("Delete")
    except Exception as exc:
        log(f"[HumanInput] keyboard clear failed ({exc})")


async def _jitter(lo: float, hi: float) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def insert_prompt_text(page, locator, text: str, logger=None) -> bool:
    """
    Put ``text`` into ``locator`` the way a person would.

    Returns True when the field verifiably contains the text afterwards.
    """
    log = (lambda msg: logger.debug(msg)) if logger else (lambda msg: None)
    expected = _normalise(text)

    await _focus(locator, log)
    await _clear(page, locator, log)

    if not expected:
        return True

    humanize = _env_flag("CAMOUFOX_HUMANIZE", True)
    type_limit = _env_int("HUMAN_TYPE_MAX_CHARS", 320)

    if len(expected) <= type_limit:
        try:
            # A short beat after focus, like a person deciding what to write.
            await _jitter(0.08, 0.30)
            delay = 0 if humanize else random.randint(25, 60)
            await page.keyboard.type(expected, delay=delay)
            if await _read_field(locator) == expected:
                log(f"[HumanInput] typed {len(expected)} chars with key events")
                return True
            log("[HumanInput] typed text did not verify; falling through")
        except Exception as exc:
            log(f"[HumanInput] keyboard.type failed: {exc}")

    # Long text, or typing did not take: use the paste/IME primitive.
    try:
        await page.keyboard.insert_text(expected)
        await asyncio.sleep(0.05)
        if await _read_field(locator) == expected:
            log(f"[HumanInput] inserted {len(expected)} chars via insert_text")
            return True
        log("[HumanInput] insert_text did not verify; falling through")
    except Exception as exc:
        log(f"[HumanInput] insert_text failed: {exc}")

    # Last resort: legacy assignment. Kept as a safety net, not the happy path.
    try:
        await locator.evaluate(_LEGACY_FILL_JS, text)
        ok = await _read_field(locator) == expected
        log(f"[HumanInput] legacy assignment used (verified={ok})")
        return ok
    except Exception as exc:
        log(f"[HumanInput] legacy assignment failed: {exc}")
        return False
