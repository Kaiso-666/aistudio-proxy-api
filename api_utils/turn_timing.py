"""
Opt-in per-turn phase timing.

Why this exists
---------------
`OPTIMIZATION.md` §6 lists six numbers that only a live run can settle: queue
wait, prep (model switch / params / session / prompt entry), TTFB, generation,
and the serialised tail between "response done" and "next request dequeued".
Reasoning about them yields ranges; marking them costs five calls and a dict.

Cost and safety
---------------
Nothing here touches the request. `mark()` is a dictionary store, `finish()`
does five subtractions, and both are no-ops in behaviour. Logging is gated on
`TURN_TIMING=1` so normal runs stay quiet; the ring buffer is kept regardless
because it is 20 small dicts and `/health` can show the last turns without
anyone having to have enabled a flag before the incident.

Phases
------
    enqueue      handler entry
    dequeued     worker picked it up          (queue wait)
    submitted    prompt entered and submitted (prep)
    first_byte   first stream item arrived    (TTFB)
    done         response complete            (generation)
    finish       post-turn work finished      (tail)

Any phase may be absent - a non-streaming turn has no `first_byte`, a failed
turn may have only two. Deltas are reported only when both ends exist.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Deque, Dict, Optional

MAX_TRACKED = 64
RING_SIZE = 20

_PHASES = ("enqueue", "dequeued", "submitted", "first_byte", "done", "finish")

_state: Dict[str, Dict[str, float]] = {}
_ring: Deque[dict] = deque(maxlen=RING_SIZE)


def enabled() -> bool:
    return os.environ.get("TURN_TIMING", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
        "y",
    )


def begin(req_id: str) -> None:
    """Start tracking a turn. Call from the request handler, before queueing."""
    _state[req_id] = {"enqueue": time.monotonic()}
    if len(_state) > MAX_TRACKED:
        # A turn that never reached `finish` (cancelled request, crashed worker)
        # must not leak. Drop the oldest, which is the least likely to be useful.
        for stale in list(_state)[: len(_state) - MAX_TRACKED]:
            _state.pop(stale, None)


def mark(req_id: str, phase: str) -> None:
    """Record one phase. Unknown request ids are tracked from their first mark."""
    if phase not in _PHASES:
        return
    entry = _state.get(req_id)
    if entry is None:
        entry = _state.setdefault(req_id, {})
    entry.setdefault("enqueue", time.monotonic())
    entry.setdefault(phase, time.monotonic())


def _delta(entry: Dict[str, float], start: str, end: str) -> Optional[float]:
    if start in entry and end in entry:
        return round(entry[end] - entry[start], 3)
    return None


def finish(req_id: str, logger=None, extra: Optional[dict] = None) -> Optional[dict]:
    """Close a turn, append it to the ring, and log when TURN_TIMING is on."""
    entry = _state.pop(req_id, None)
    if entry is None:
        return None
    entry.setdefault("finish", time.monotonic())

    record = {
        "req": req_id,
        "queue_s": _delta(entry, "enqueue", "dequeued"),
        "prep_s": _delta(entry, "dequeued", "submitted"),
        "ttfb_s": _delta(entry, "submitted", "first_byte"),
        "gen_s": _delta(entry, "first_byte", "done"),
        "tail_s": _delta(entry, "done", "finish"),
        "total_s": _delta(entry, "enqueue", "finish"),
    }
    if extra:
        record.update(extra)
    _ring.append(record)

    if enabled() and logger is not None:
        parts = [
            f"{key}={value}"
            for key, value in record.items()
            if key != "req" and value is not None
        ]
        logger.info(f"[{req_id}] [TIMING] {' '.join(parts)}")
    return record


def recent(limit: int = RING_SIZE) -> list:
    """Most recent turns, oldest first."""
    items = list(_ring)
    return items[-limit:] if limit else items


def summary() -> dict:
    """Median-ish view of the ring, cheap enough for /health."""
    turns = [r for r in _ring if r.get("total_s") is not None]
    if not turns:
        return {"turns": 0, "recent": recent(5)}

    def median(key: str) -> Optional[float]:
        values = sorted(r[key] for r in turns if r.get(key) is not None)
        if not values:
            return None
        return values[len(values) // 2]

    return {
        "turns": len(turns),
        "queue_s": median("queue_s"),
        "prep_s": median("prep_s"),
        "ttfb_s": median("ttfb_s"),
        "gen_s": median("gen_s"),
        "tail_s": median("tail_s"),
        "total_s": median("total_s"),
        "recent": recent(5),
    }
