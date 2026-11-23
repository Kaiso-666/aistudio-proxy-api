from typing import Any, Dict, List, Optional

from models import Message


def validate_chat_request(
    messages: List[Message], req_id: str
) -> Dict[str, Optional[str]]:
    if not messages:
        raise ValueError(
            f"[{req_id}] Invalid request: 'messages' array is missing or empty."
        )

    if not any(msg.role != "system" for msg in messages):
        raise ValueError(
            f"[{req_id}] Invalid request: All messages are system messages. At least one user or assistant message is required."
        )

    return {"error": None, "warning": None}


def validate_supported_features(request: Any, req_id: str) -> None:
    """Reject request features this transport cannot honour.

    Everything checked here has no representation in the AI Studio page or its
    RPC: one generation per turn, no logit access, no presence/frequency
    penalties. Returning 200 while ignoring the knob makes the client reason
    about a response it did not ask for, which is worse than an error it can
    handle. `user` is exempt - it is only a cache key in OpenAI's API.
    """
    n = getattr(request, "n", None)
    if n not in (None, 1):
        raise ValueError(
            f"`n={n}` is not supported: the proxy returns exactly one choice."
        )

    if getattr(request, "logprobs", None) or getattr(request, "top_logprobs", None):
        raise ValueError(
            "`logprobs`/`top_logprobs` are not supported: the web client exposes "
            "no logit data."
        )

    for field in ("presence_penalty", "frequency_penalty"):
        value = getattr(request, field, None)
        if value not in (None, 0, 0.0):
            raise ValueError(
                f"`{field}={value}` is not supported: AI Studio exposes no penalty "
                "control, and faking it via temperature would change the request."
            )

    if getattr(request, "parallel_tool_calls", None) is False:
        raise ValueError(
            "`parallel_tool_calls=false` is not supported: the model decides how "
            "many calls to emit and the proxy cannot force a single one."
        )
