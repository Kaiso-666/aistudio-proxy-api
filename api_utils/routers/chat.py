import asyncio
import logging
import random
import time
from asyncio import Future, Queue

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from config import RESPONSE_COMPLETION_TIMEOUT, get_environment_variable
from logging_utils import set_request_id, set_source
from models import ChatCompletionRequest

from ..dependencies import (
    ensure_request_lock,
    get_logger,
    get_request_queue,
    get_server_state,
    get_worker_task,
)
from ..error_utils import service_unavailable
from .. import turn_timing


async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    logger: logging.Logger = Depends(get_logger),
    request_queue: Queue = Depends(get_request_queue),
    server_state: dict = Depends(get_server_state),
    worker_task=Depends(get_worker_task),
    _lock: None = Depends(ensure_request_lock),
) -> JSONResponse:
    req_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=7))

    # Set log context (Grid Logger)
    set_request_id(req_id)
    set_source("API")

    logger.info(f"Received /v1/chat/completions request (Stream={request.stream})")

    launch_mode = get_environment_variable("LAUNCH_MODE", "unknown")
    browser_page_critical = launch_mode != "direct_debug_no_browser"

    is_service_unavailable = (
        server_state["is_initializing"]
        or not server_state["is_playwright_ready"]
        or (
            browser_page_critical
            and (
                not server_state["is_page_ready"]
                or not server_state["is_browser_connected"]
            )
        )
        or not worker_task
        or worker_task.done()
    )

    if is_service_unavailable:
        raise service_unavailable(req_id)

    # Admission control. The worker serialises to one browser context, so a
    # queue deeper than a few turns only converts a fast 429 into a long hang
    # the client has already abandoned by the time its turn starts. Rejecting
    # early gives the harness a retryable signal instead of a mystery stall.
    try:
        max_depth = int(get_environment_variable("MAX_QUEUE_DEPTH", "3") or 0)
    except (TypeError, ValueError):
        max_depth = 3
    depth = request_queue.qsize() if request_queue else 0
    if max_depth > 0 and depth >= max_depth:
        logger.warning(
            f"[{req_id}] Rejecting request: queue depth {depth} >= {max_depth}."
        )
        raise HTTPException(
            status_code=429,
            detail=f"[{req_id}] Proxy busy: {depth} requests already queued.",
            headers={"Retry-After": "20"},
        )

    result_future = Future()
    turn_timing.begin(req_id)
    queue_item = {
        "req_id": req_id,
        "request_data": request,
        "http_request": http_request,
        "result_future": result_future,
        "enqueue_time": time.time(),
        "cancelled": False,
    }
    await request_queue.put(queue_item)

    try:
        timeout_seconds = RESPONSE_COMPLETION_TIMEOUT / 1000 + 120
        return await asyncio.wait_for(result_future, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504, detail=f"[{req_id}] Request processing timed out."
        )
    except asyncio.CancelledError:
        logger.info(f"Request cancelled by client: {req_id}")
        raise
    except HTTPException as http_exc:
        if http_exc.status_code == 499:
            logger.info(f"Client disconnected: {http_exc.detail}")
        else:
            logger.warning(f"HTTP exception: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.exception("Error waiting for Worker response")
        raise HTTPException(
            status_code=500, detail=f"[{req_id}] Internal server error: {e}"
        )
