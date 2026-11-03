"""
Conversation-affine chat sessions with context-window rotation.

Why this exists
---------------
Upstream cleared the AI Studio chat after *every* request and re-serialised the
entire `messages` array into a single prompt. For a one-shot caller that is
merely wasteful. For an agent loop it is O(n^2) input tokens: turn N re-uploads
turns 1..N-1 as fresh text, so a 20-turn run sends roughly ten times the tokens a
persistent chat would, re-types or re-pastes the whole transcript every call,
and burns the quota-rotation thresholds proportionally faster.

The model
---------
A *session* is a chat that is allowed to stay loaded in the page. Two things are
tracked per session:

  client_fps   fingerprints of every message the client has sent so far
  page_len     how many of those messages the page actually holds, plus one when
               the page also holds the assistant reply the client has not sent
               back yet
  base_index   the client index at which the page's own transcript begins;
               everything before it is represented by `handoff`
  handoff      a summary produced at the last rotation, or ""

On a new request:

  * derive a stable key from the conversation's leading context
    (system prompt + first user message + model + tool signature),
  * if the stored fingerprints are a strict prefix of the incoming ones, submit
    only `messages[page_len:]` - the page already holds the rest,
  * otherwise replay everything into a cleared chat.

The prefix test is what makes this safe. An agent that rewrites, truncates or
reorders history fails the test and gets a full replay; it can never silently
inherit a chat whose contents have diverged. Delta is used only when provably a
continuation.

Rotation
--------
Modern models carry ~1M tokens, so a chat is kept until the *page* approaches
that budget. At ~900k the caller runs one summarisation turn in the same chat,
then clears it and seeds the next chat with the summary. The summary therefore
covers the previous handoff as well and chains naturally across rotations, which
is what keeps a long agent run coherent instead of degrading every 900k tokens.

Stateless callers are unaffected: a request whose history does not extend a known
prefix resolves to a full replay, exactly as upstream behaved.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

# --- knobs -----------------------------------------------------------------

MAX_SESSIONS = int(os.environ.get("SESSION_MAX_ACTIVE", "6") or 6)
SESSION_TTL = float(os.environ.get("SESSION_TTL_SECONDS", "1800") or 1800)

# Rotation policy. 900k leaves headroom for the summarisation turn itself, the
# reply, and the seed block, inside a 1M window.
CONTEXT_LIMIT_TOKENS = int(
    os.environ.get("SESSION_CONTEXT_LIMIT_TOKENS", "900000") or 900000
)
CHARS_PER_TOKEN = float(os.environ.get("SESSION_CHARS_PER_TOKEN", "3.5") or 3.5)

HANDOFF_PREFIX = (
    "[CONTEXT HANDOFF]\n"
    "The previous conversation has been compacted to stay within the context "
    "window. Below is a summary produced by the previous session. Treat it as "
    "established fact, do not re-ask for it, and continue the task from where "
    "it left off.\n\n"
)
HANDOFF_SUFFIX = "\n[/CONTEXT HANDOFF]\n\nContinue the task. Next turn:\n"

SUMMARY_INSTRUCTION = (
    "Summarise this entire conversation as a context handoff for a fresh "
    "session that must continue the same task. Preserve, in this order: the "
    "original goal and constraints; decisions taken and why; current state of "
    "the work; concrete data needed to continue (paths, ids, values, names); "
    "open questions and next steps. Be complete but compact - omit "
    "pleasantries and repetition. Output only the summary."
)


def reuse_enabled() -> bool:
    """SESSION_REUSE_ENABLED=false restores upstream's clear-every-request."""
    return os.environ.get("SESSION_REUSE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
        "y",
    )


def rotation_enabled() -> bool:
    return os.environ.get("SESSION_ROTATE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
        "y",
    )


# --- data ------------------------------------------------------------------


@dataclass
class Session:
    key: str
    model: str
    tools_hash: str
    client_fps: tuple = ()
    page_len: int = 0
    base_index: int = 0
    handoff: str = ""
    seeded: bool = True
    turns: int = 0
    page_tokens: int = 0
    last_used: float = field(default_factory=time.time)


@dataclass
class Resolution:
    """What to submit now, and what has to happen to the page first."""

    key: Optional[str]
    messages: List[Any]
    mode: str  # "full" | "delta"
    reused: bool = False
    needs_clear: bool = False
    seed_prefix: str = ""
    rotation_due: bool = False
    page_tokens: int = 0
    est_tokens: int = 0


@dataclass
class PendingCommit:
    """Stashed by the request path, applied once the response is complete."""

    resolution: Resolution
    messages: List[Any]
    model: str
    tools: Any
    created: float = field(default_factory=time.time)


_sessions: "OrderedDict[str, Session]" = OrderedDict()
_active_key: Optional[str] = None
_pending: Optional[PendingCommit] = None
# Whether the live page holds any turn at all. Tracked instead of probing the
# DOM: a clear costs ~4s, and a probe is wrong while Angular is animating.
_page_dirty: bool = False


# --- helpers ---------------------------------------------------------------


def _content_signature(message: Any) -> str:
    """Stable hash of everything that affects what the model sees in a turn."""
    role = getattr(message, "role", "") or ""
    content = getattr(message, "content", None)
    tool_calls = getattr(message, "tool_calls", None)
    parts = [role]

    if isinstance(content, str):
        parts.append(content)
    elif content is None:
        parts.append("")
    else:
        try:
            parts.append(
                json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
            )
        except Exception:
            parts.append(str(content))

    if tool_calls:
        try:
            parts.append(
                json.dumps(tool_calls, sort_keys=True, ensure_ascii=False, default=str)
            )
        except Exception:
            parts.append(str(tool_calls))

    digest = hashlib.sha256("\x00".join(parts).encode("utf-8", "replace")).hexdigest()
    return digest[:32]


def _fingerprints(messages: Sequence[Any]) -> tuple:
    return tuple(_content_signature(m) for m in messages)


def _tools_hash(tools: Optional[Sequence[dict]]) -> str:
    if not tools:
        return "none"
    try:
        blob = json.dumps(tools, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        blob = str(tools)
    return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


def _derive_key(messages: Sequence[Any], model: str, tools_hash: str) -> Optional[str]:
    """
    Key on the stable head of the conversation.

    Agents resend their whole history each turn, so the system prompt plus the
    first user message identifies the conversation; later turns are the part
    that grows. A single-shot request still produces a key, but its history will
    never be a strict prefix of itself, so it resolves to a full replay.
    """
    if not messages:
        return None

    head: List[str] = []
    for m in messages:
        if getattr(m, "role", "") == "system":
            head.append(_content_signature(m))

    first_user = next((m for m in messages if getattr(m, "role", "") == "user"), None)
    if first_user is None:
        return None
    head.append(_content_signature(first_user))

    blob = "\x00".join(head + [model or "", tools_hash])
    return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:24]


def _is_strict_prefix(old: tuple, new: tuple) -> bool:
    return len(old) < len(new) and new[: len(old)] == old


def _expire() -> None:
    now = time.time()
    for key in [k for k, s in _sessions.items() if now - s.last_used > SESSION_TTL]:
        _sessions.pop(key, None)


def estimate_tokens(messages: Sequence[Any]) -> int:
    """
    Rough token count for a message list.

    Character-based on purpose: it needs to be monotonic and cheap, not exact.
    Being wrong by 10% only shifts the rotation point slightly; the hard limit
    is enforced by the model anyway.
    """
    chars = 0
    for m in messages:
        content = getattr(m, "content", None)
        if isinstance(content, str):
            chars += len(content)
        elif content is not None:
            try:
                chars += len(json.dumps(content, ensure_ascii=False, default=str))
            except Exception:
                chars += len(str(content))
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            try:
                chars += len(json.dumps(tool_calls, ensure_ascii=False, default=str))
            except Exception:
                chars += len(str(tool_calls))
    return int(chars / CHARS_PER_TOKEN)


def handoff_prompt(summary: str, next_turn_text: str) -> str:
    return f"{HANDOFF_PREFIX}{summary.strip()}{HANDOFF_SUFFIX}{next_turn_text}"


# --- resolution ------------------------------------------------------------


def resolve(req_id: str, messages: Sequence[Any], model: str, tools) -> Resolution:
    """Decide whether this request continues a loaded chat or starts a new one."""
    messages = list(messages)
    est = estimate_tokens(messages)
    full_replay = Resolution(
        key=None,
        messages=messages,
        mode="full",
        needs_clear=True,
        rotation_due=est >= CONTEXT_LIMIT_TOKENS,
        page_tokens=est,
        est_tokens=est,
    )

    if not reuse_enabled() or not messages:
        return full_replay

    tools_h = _tools_hash(tools)
    key = _derive_key(messages, model, tools_h)
    if not key:
        return full_replay

    _expire()
    session = _sessions.get(key)
    fps = _fingerprints(messages)

    if session is None or session.model != model or session.tools_hash != tools_h:
        full_replay.key = key
        return full_replay

    if not _is_strict_prefix(session.client_fps, fps):
        # History was rewritten, truncated, or is an exact repeat. Replay.
        full_replay.key = key
        return full_replay

    if session.page_len < session.base_index:
        # Inconsistent bookkeeping (should not happen). Never guess.
        full_replay.key = key
        return full_replay

    delta = messages[session.page_len :]
    if not delta:
        # The client resent the history plus the reply we already have, with no
        # new turn. Replaying everything would re-upload the pre-compaction
        # history that the handoff exists to avoid.
        if session.base_index > 0 and len(messages) > session.base_index:
            return Resolution(
                key=key,
                messages=messages[session.base_index :],
                mode="full",
                needs_clear=True,
                seed_prefix=(
                    HANDOFF_PREFIX + session.handoff + HANDOFF_SUFFIX
                    if session.handoff
                    else ""
                ),
                rotation_due=False,
                page_tokens=session.page_tokens,
                est_tokens=est,
            )
        full_replay.key = key
        return full_replay

    page_tokens = estimate_tokens(messages[session.base_index :]) + estimate_tokens(
        [session.handoff] if session.handoff else []
    )
    seeded = session.seeded and session.page_len > session.base_index

    return Resolution(
        key=key,
        messages=delta,
        mode="delta",
        reused=True,
        needs_clear=False,
        seed_prefix="" if seeded else HANDOFF_PREFIX + session.handoff + HANDOFF_SUFFIX,
        rotation_due=page_tokens >= CONTEXT_LIMIT_TOKENS,
        page_tokens=page_tokens,
        est_tokens=est,
    )


# --- commit ----------------------------------------------------------------


def stash(resolution: Resolution, messages: Sequence[Any], model: str, tools) -> None:
    """Remember what was just submitted so it can be committed on success."""
    global _pending
    _pending = PendingCommit(
        resolution=resolution, messages=list(messages), model=model, tools=tools
    )


def commit_pending() -> Optional[Session]:
    """
    The submitted turn is now fully in the page.

    `page_len` advances by len(messages) + 1: the extra one is the assistant
    reply, which the client has not sent back yet. Counting it prevents the next
    delta from re-submitting the model's own answer as a new turn.
    """
    global _pending, _active_key, _page_dirty
    if _pending is None:
        return None

    pending = _pending
    _pending = None
    resolution = pending.resolution
    if not resolution.key:
        return None

    messages = pending.messages
    fps = _fingerprints(messages)

    session = _sessions.get(resolution.key)
    if session is None or resolution.mode == "full":
        session = Session(
            key=resolution.key,
            model=pending.model,
            tools_hash=_tools_hash(pending.tools),
            client_fps=fps,
            page_len=len(messages) + 1,
            base_index=0,
            handoff="",
            seeded=True,
        )
        _sessions[resolution.key] = session
    else:
        session.client_fps = fps
        session.page_len = len(messages) + 1
        session.turns += 1
        session.seeded = True
        session.last_used = time.time()
        _sessions.move_to_end(resolution.key)

    # Token estimate of what the page is physically holding, measured in the
    # client's coordinate space (everything before `base_index` is compressed
    # into `handoff` and therefore not part of the page transcript).
    tail = messages[session.base_index :]
    session.page_tokens = estimate_tokens(tail) + estimate_tokens(
        [session.handoff] if session.handoff else []
    )
    session.seeded = True
    session.last_used = time.time()
    _page_dirty = True

    _active_key = resolution.key

    while len(_sessions) > MAX_SESSIONS:
        _, evicted = _sessions.popitem(last=False)
        if _active_key == evicted.key:
            _active_key = None

    return session


def drop_pending() -> None:
    """The turn failed after submission; the page may hold a partial answer."""
    global _pending, _page_dirty
    _pending = None
    _page_dirty = True


# --- rotation --------------------------------------------------------------


def rotation_candidate() -> Optional[Session]:
    """
    Session that should be compacted now, if any.

    Evaluated after a successful commit so the summarisation turn sees the
    completed reply. `page_tokens` only counts what is physically in the chat,
    so a session that has already been compacted keeps counting from the new
    base instead of from the client's (ever-growing) full history.
    """
    if not rotation_enabled():
        return None
    if _pending is not None:
        return None
    key = _active_key
    if not key:
        return None
    session = _sessions.get(key)
    if session is None or not session.client_fps:
        return None
    if session.page_len <= session.base_index:
        return None
    if session.page_tokens < CONTEXT_LIMIT_TOKENS:
        return None
    return session


def apply_rotation(key: str, summary: str) -> Optional[Session]:
    """
    Mark the chat as compacted: the page will be cleared, and the next request
    is seeded with `summary`.
    """
    session = _sessions.get(key)
    if session is None:
        return None
    session.base_index = max(session.page_len, session.base_index)
    session.handoff = summary.strip()
    session.seeded = False
    session.turns = 0
    session.page_len = session.base_index
    session.page_tokens = estimate_tokens([session.handoff])
    session.last_used = time.time()
    _sessions.move_to_end(key)
    return session


def invalidate(key: Optional[str] = None) -> None:
    """
    Drop a session so the next use starts from a cleared chat.

    Called on any failure between "prompt submitted" and "response captured":
    the page may hold a half-finished turn, and reusing it would feed garbage
    context into the next request.
    """
    global _active_key, _pending, _page_dirty
    _pending = None
    _page_dirty = True
    if key is None:
        _sessions.clear()
        _active_key = None
        return
    _sessions.pop(key, None)
    if _active_key == key:
        _active_key = None


def set_active(key: Optional[str]) -> None:
    global _active_key
    _active_key = key


def page_dirty() -> bool:
    return _page_dirty


def set_page_dirty(dirty: bool = True) -> None:
    """Record whether the live chat holds turns that a replay would duplicate."""
    global _page_dirty
    _page_dirty = dirty


def active_key() -> Optional[str]:
    return _active_key


def stats() -> dict:
    return {
        "sessions": len(_sessions),
        "active": _active_key,
        "page_dirty": _page_dirty,
        "reuse_enabled": reuse_enabled(),
        "rotation_enabled": rotation_enabled(),
        "limit_tokens": CONTEXT_LIMIT_TOKENS,
        "entries": [
            {
                "key": s.key,
                "model": s.model,
                "turns": s.turns,
                "page_len": s.page_len,
                "base_index": s.base_index,
                "handoff_chars": len(s.handoff),
                "seeded": s.seeded,
            }
            for s in _sessions.values()
        ],
    }
