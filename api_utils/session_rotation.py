"""
Context-window rotation.

When a session's *page* approaches the model's context budget (~900k of ~1M
tokens), the proxy asks the model - in the chat that already holds the context -
for a handoff summary, then clears the chat and seeds the next one with it.

Doing the summary in-place is the whole trick: the model already has the entire
conversation, so the summary costs one ordinary turn and no re-upload. It also
chains naturally - the seed block from the previous rotation is part of what the
model is summarising, so information survives rotation after rotation.

Runs between queued requests, while the worker owns the page, so it can never
interleave with a client turn.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from api_utils import chat_sessions

# Summarising 900k tokens is a long turn; the output itself is bounded.
SUMMARY_TIMEOUT_S = float(360.0)
SUMMARY_SILENCE_S = float(120.0)
MIN_SUMMARY_CHARS = 40


async def _collect_from_stream(
    req_id: str, page, started_at: float, logger
) -> str:
    """Drain the aux stream queue produced by the summarisation turn."""
    from api_utils.server_state import state

    if state.STREAM_QUEUE is None:
        return ""

    from api_utils.utils_ext.stream import use_stream_response

    body = ""
    async for chunk in use_stream_response(
        req_id,
        timeout=SUMMARY_TIMEOUT_S,
        silence_threshold=SUMMARY_SILENCE_S,
        page=page,
        check_client_disconnected=None,
        stream_start_time=started_at,
        enable_silence_detection=True,
    ):
        if not isinstance(chunk, dict):
            continue
        # `body` is cumulative in this generator, so keep the longest one.
        candidate = str(chunk.get("body") or "")
        if len(candidate) > len(body):
            body = candidate
        if chunk.get("done") is True:
            logger.debug(f"[{req_id}] [Session] Summary stream done")
            break
    return body.strip()


async def _collect_from_dom(page, req_id: str, logger) -> str:
    """Fallback when the stream proxy is disabled: poll the rendered answer."""
    from browser_utils.page_controller import PageController

    controller = PageController(page, logger, req_id)
    deadline = time.time() + SUMMARY_TIMEOUT_S
    last_text = ""
    stable_since = time.time()
    while time.time() < deadline:
        try:
            text = (await controller.get_body_text_only_from_dom()) or ""
        except Exception:
            text = ""
        if text != last_text:
            last_text = text
            stable_since = time.time()
        elif text and time.time() - stable_since > 3.0:
            stop = page.locator('button[aria-label="Stop generating"]')
            try:
                if await stop.count() == 0:
                    break
            except Exception:
                break
        await asyncio.sleep(0.5)
    return last_text.strip()


async def _wait_for_idle(page, logger, req_id: str, timeout: float = 60.0) -> None:
    """Wait until the Run control is clickable again (generation finished)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            stop = page.locator('button[aria-label="Stop generating"]')
            if await stop.count() == 0:
                return
        except Exception:
            return
        await asyncio.sleep(0.25)


async def run_rotation(page, req_id: str, logger) -> bool:
    """
    Compact the active session if it is over budget. Returns True if it rotated.

    A failure here never propagates: the client's turn has already been served,
    and the worst case is a full replay on the next request (the session is
    invalidated so the page cannot be trusted).
    """
    session = chat_sessions.rotation_candidate()
    if session is None:
        return False

    key = session.key
    logger.info(
        f"[{req_id}] [Session] Context rotation: ~{session.page_tokens} page "
        f"tokens >= {chat_sessions.CONTEXT_LIMIT_TOKENS}; compacting."
    )

    from browser_utils.page_controller import PageController

    controller = PageController(page, logger, req_id)
    started_at = time.time()

    try:
        await _wait_for_idle(page, logger, req_id)
        await controller.submit_prompt(
            chat_sessions.SUMMARY_INSTRUCTION, [], lambda stage: False
        )
    except Exception as e:
        logger.warning(f"[{req_id}] [Session] Summary submit failed: {e}")
        chat_sessions.invalidate(key)
        return False

    try:
        summary = await _collect_from_stream(req_id, page, started_at, logger)
        if len(summary) < MIN_SUMMARY_CHARS:
            dom_text = await _collect_from_dom(page, req_id, logger)
            if len(dom_text) > len(summary):
                summary = dom_text
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[{req_id}] [Session] Summary capture failed: {e}")
        summary = ""

    if len(summary) < MIN_SUMMARY_CHARS:
        logger.warning(
            f"[{req_id}] [Session] Rotation aborted (summary too short: "
            f"{len(summary)} chars); next request will replay."
        )
        chat_sessions.invalidate(key)
        try:
            await controller.clear_chat_history(lambda stage: False)
        except Exception:
            pass
        return False

    chat_sessions.apply_rotation(key, summary)
    logger.info(
        f"[{req_id}] [Session] Handoff stored: {len(summary)} chars, "
        f"base_index={session.base_index}"
    )

    try:
        await controller.clear_chat_history(lambda stage: False)
        chat_sessions.set_page_dirty(False)
        logger.info(f"[{req_id}] [Session] Chat cleared for the new context window.")
        return True
    except Exception as e:
        logger.warning(f"[{req_id}] [Session] Clear after rotation failed: {e}")
        chat_sessions.invalidate(key)
        return False


async def maybe_rotate(page, req_id: str, logger) -> bool:
    """Entry point used by the queue worker."""
    try:
        return await run_rotation(page, req_id, logger)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"[{req_id}] [Session] Rotation error: {e}")
        return False
