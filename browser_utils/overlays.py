# --- browser_utils/overlays.py ---
"""
Dismiss modal dialogs that block the AI Studio prompt area.

AI Studio presents an upsell dialog ("Go further with AI Studio") on fresh
sessions. It is an Angular Material dialog rendered inside
`.cdk-overlay-container` with a blurred `.cdk-overlay-backdrop` that captures
pointer events for the whole viewport.

Consequences if left open:

  * the Run button never becomes enabled, because the app still considers the
    prompt "not committable" while a dialog owns focus, and
  * every `locator.click()` either lands on the backdrop or times out on
    actionability checks.

Escape does not work: these dialogs are created with `disableClose`, so the
only reliable exit is the explicit `button[aria-label="close"]` in the dialog
header. This module clicks it, tolerating the absence of any dialog.
"""

import asyncio

_CLOSE_BUTTON_SELECTORS = (
    "ms-upgrade-options-dialog button[aria-label='close']",
    "mat-dialog-container button[aria-label='close']",
    ".cdk-overlay-pane button[aria-label='close']",
    "mat-dialog-container button[mat-dialog-close]",
)

# Confirmation dialogs have no close affordance: "New chat" with text still in
# the composer raises a two-button dialog ("Cancel" / "Discard and continue")
# that owns focus until one of them is clicked. Left open, every later click
# times out and the request fails with a Playwright error.
_AFFIRM_BUTTON_SELECTORS = (
    "mat-dialog-container button:has-text('Discard and continue')",
    ".cdk-overlay-pane button:has-text('Discard and continue')",
    "ms-confirm-clear-dialog button.ms-button-primary",
    "mat-dialog-container button:has-text('Discard')",
    ".cdk-overlay-pane button:has-text('Discard')",
    "mat-dialog-container button:has-text('Got it')",
    "mat-dialog-container button:has-text('Dismiss')",
    "mat-dialog-container button:has-text('OK')",
)


async def force_clear_overlays(page, logger=None) -> int:
    """
    Last resort: detach every overlay pane and backdrop.

    Used only after the polite paths failed. A stuck backdrop is worse than a
    detached dialog: every subsequent click in the request times out, so the
    proxy returns 502 on a turn that never even reached the model.
    """
    log = (lambda msg: logger.debug(msg)) if logger else (lambda msg: None)
    try:
        removed = await page.evaluate(
            """() => {
                let n = 0;
                document.querySelectorAll(
                    '.cdk-overlay-backdrop-showing, .cdk-overlay-pane'
                ).forEach(el => { el.remove(); n += 1; });
                return n;
            }"""
        )
        if removed:
            log(f"[Overlay] force-removed {removed} overlay node(s)")
        return int(removed or 0)
    except Exception:
        return 0


async def _find_clickable(page, selectors):
    for selector in selectors:
        candidate = page.locator(selector).first
        try:
            if await candidate.count() > 0 and await candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


async def dismiss_blocking_dialogs(page, logger=None, max_dialogs: int = 3) -> int:
    """
    Close any open Material dialog. Returns the number dismissed.

    Loops because a second dialog can mount immediately after the first one
    unmounts (`mat-dialog` animations are 150ms, so we wait for the pane to
    detach rather than assuming a fixed delay).
    """
    log = (lambda msg: logger.debug(msg)) if logger else (lambda msg: None)
    dismissed = 0

    for _ in range(max_dialogs):
        button = await _find_clickable(page, _CLOSE_BUTTON_SELECTORS)
        if button is None:
            # Second pass: a confirmation dialog with no close affordance. Only
            # the "discard the composer contents" variant is clicked - it is
            # raised by our own New-chat navigation and is safe to accept.
            button = await _find_clickable(page, _AFFIRM_BUTTON_SELECTORS)
            if button is not None:
                log("[Overlay] dismissing confirmation dialog (discard)")
        if button is None:
            break

        try:
            await button.click(timeout=3000)
            dismissed += 1
            log(f"[Overlay] dismissed dialog via close button ({dismissed})")
        except Exception as exc:
            log(f"[Overlay] close button click failed: {exc}")
            break

        # Wait for the dialog pane itself to go away, not a fixed sleep.
        try:
            await page.wait_for_selector(
                ".cdk-overlay-pane mat-dialog-container",
                state="detached",
                timeout=3000,
            )
        except Exception:
            await asyncio.sleep(0.4)

    # Closing a dialog can leave its backdrop mounted (the click races the
    # Angular teardown). A transparent backdrop with no dialog pane behind it
    # intercepts every pointer event, so the page looks frozen: Run never
    # enables and each click times out on actionability. Remove those, but only
    # when no real dialog is present - a live dialog still owns its backdrop.
    try:
        removed = await page.evaluate(
            """() => {
                const panes = Array.from(
                    document.querySelectorAll('.cdk-overlay-pane')
                ).filter(p => p.querySelector('mat-dialog-container'));
                if (panes.length) return 0;
                const bds = Array.from(
                    document.querySelectorAll('.cdk-overlay-backdrop-showing')
                );
                bds.forEach(b => b.remove());
                return bds.length;
            }"""
        )
        if removed:
            log(f"[Overlay] removed {removed} leaked backdrop(s)")
    except Exception:
        pass

    return dismissed


async def overlay_is_blocking(page) -> bool:
    """True when a dialog backdrop is currently intercepting pointer events."""
    try:
        backdrop = page.locator("div.cdk-overlay-backdrop-showing")
        return await backdrop.count() > 0
    except Exception:
        return False
