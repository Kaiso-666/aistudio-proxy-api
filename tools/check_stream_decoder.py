"""Regression check for the stream wire decoder (stream/interceptors.py).

The MITM child discards its stderr, so a decoder defect here shows up only as
"the answer was cut / repeated / timed out" in a client. This script loads the
module with stubbed imports (no project dependencies) and re-plays bodies in
byte-sized reads the way `stream/proxy_server.py` feeds it: **cumulative**, i.e.
each call receives the body accumulated since the start of the response.

Run from the repository root:

    python3 tools/check_stream_decoder.py

Exit code 0 = every case matched; 1 = a case failed (details printed).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import pathlib
import sys
import types
import zlib

REPO = pathlib.Path(__file__).resolve().parent.parent


# --- stubs for the module's imports ----------------------------------------
def _install_stubs() -> None:
    gs = types.ModuleType("config.global_state")

    class GlobalState:  # noqa: D101 - stub
        IS_QUOTA_EXCEEDED = False
        IS_RECOVERING = False
        CURRENT_STREAM_REQ_ID = None

    gs.GlobalState = GlobalState

    settings = types.ModuleType("config.settings")
    settings.FUNCTION_CALLING_DEBUG = False

    config = types.ModuleType("config")
    config.global_state = gs
    config.settings = settings

    fc_debug = types.ModuleType("logging_utils.fc_debug")

    class _FC:
        def log_wire_parse(self, **_kwargs):
            pass

    fc_debug.get_fc_logger = lambda: _FC()

    grid = types.ModuleType("logging_utils.grid_logger")

    class GridFormatter(logging.Formatter):
        def __init__(self, *args, **kwargs):
            super().__init__()

    grid.GridFormatter = GridFormatter

    logging_utils = types.ModuleType("logging_utils")
    logging_utils.fc_debug = fc_debug
    logging_utils.grid_logger = grid

    modules = {
        "config": config,
        "config.global_state": gs,
        "config.settings": settings,
        "logging_utils": logging_utils,
        "logging_utils.fc_debug": fc_debug,
        "logging_utils.grid_logger": grid,
    }
    sys.modules.update(modules)


def _load_interceptor():
    _install_stubs()
    spec = importlib.util.spec_from_file_location(
        "_ic", REPO / "stream" / "interceptors.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ic"] = module
    spec.loader.exec_module(module)
    logging.getLogger("http_interceptor").setLevel(logging.CRITICAL)
    return module


ic = _load_interceptor()


# --- wire construction ------------------------------------------------------
def body_frame(text: str) -> bytes:
    return ('[[[null,%s]],"model"]' % json.dumps(text)).encode()


def reason_frame(text: str) -> bytes:
    return ('[[[null,%s,null]],"model"]' % json.dumps(text)).encode()


def call_frame(name: str, args: list) -> bytes:
    payload = [None, None] + [None] * 8 + [[name, args]]
    # The payload is inlined after the leading null, not nested as a list:
    # the parsed shape is `json_data[0][0]` and it must have length 11.
    rest = ",".join(json.dumps(item) for item in payload[1:])
    return ('[[[null,%s]],"model"]' % rest).encode()


def chunk(payload: bytes, ext: bytes = b"") -> bytes:
    return b"%x%s\r\n%s\r\n" % (len(payload), ext, payload)


def encode(payload: bytes, size: int = 9, compress: bool = True, tail: bytes = b"0\r\n\r\n") -> bytes:
    data = zlib.compress(payload) if compress else payload
    out = b"".join(chunk(data[i : i + size]) for i in range(0, len(data), size))
    return out + tail


# --- harness ---------------------------------------------------------------
FAILURES: list[str] = []


def check(name: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}\n       expected={expected!r}\n       actual  ={actual!r}")
        FAILURES.append(name)


async def replay(wire: bytes, step: int) -> tuple[str, str, bool, list]:
    """Feed the body in cumulative reads; return (body, reason, done, calls)."""
    interceptor = ic.HttpInterceptor(log_dir="/tmp/none")
    body = reason = ""
    done = False
    calls: list = []
    for cut in range(step, len(wire), step):
        result = await interceptor.process_response(wire[:cut], "host", "", {})
        body += result["body"]
        reason += result["reason"]
        done = done or bool(result["done"])
        calls = result["function"] or calls
    result = await interceptor.process_response(wire, "host", "", {})
    body += result["body"]
    reason += result["reason"]
    done = done or bool(result["done"])
    calls = result["function"] or calls
    return body, reason, done, calls


async def main() -> int:
    text = "The quick brown fox jumps over the lazy dog. " * 4
    frames = [text[i : i + 7] for i in range(0, len(text), 7)]
    payload = b"".join(body_frame(part) for part in frames)

    print("single read")
    body, reason, done, _ = await replay(encode(payload), len(encode(payload)))
    check("text intact", body, text)
    check("complete", done, True)

    print("cumulative reads, 7 bytes at a time")
    body, reason, done, _ = await replay(encode(payload, size=7), 7)
    check("no duplication or loss", body, text)
    check("complete", done, True)

    print("cumulative reads, one byte at a time")
    body, reason, done, _ = await replay(encode(payload, size=9), 1)
    check("no duplication or loss", body, text)
    check("complete", done, True)

    print("chunk extensions")
    data = zlib.compress(payload)
    wire = chunk(data[: len(data) // 2], ext=b";foo=bar") + chunk(data[len(data) // 2 :], ext=b";x")
    body, reason, done, _ = await replay(wire + b"0\r\n\r\n", 11)
    check("text intact", body, text)
    check("complete", done, True)

    print("trailers after the terminal chunk")
    body, reason, done, _ = await replay(
        encode(payload, tail=b"0\r\ngrpc-status: 0\r\ngrpc-message: ok\r\n\r\n"), 13
    )
    check("text intact", body, text)
    check("complete", done, True)

    print("identity (uncompressed) body")
    body, reason, done, _ = await replay(encode(payload, compress=False), 17)
    check("text intact", body, text)
    check("complete", done, True)

    print("multi-byte character split across reads")
    unicode_text = "héllo wörld — ünïcode ✓"
    upayload = b"".join(body_frame(unicode_text[i : i + 3]) for i in range(0, len(unicode_text), 3))
    body, reason, done, _ = await replay(encode(upayload, size=5), 1)
    check("no mojibake or loss", body, unicode_text)
    check("complete", done, True)

    print("reasoning frames interleaved with body")
    payload = reason_frame("thinking ") + body_frame("answer") + reason_frame("more")
    body, reason, done, _ = await replay(encode(payload, size=6), 5)
    check("body", body, "answer")
    check("reasoning is a delta stream, not duplicated", reason, "thinking more")
    check("complete", done, True)

    print("function call frame")
    payload = body_frame("") + call_frame("get_weather", [["city", "Paris"]])
    body, reason, done, calls = await replay(encode(payload, size=8), 9)
    check("one call on done", [c.get("name") for c in calls], ["get_weather"])
    check("call params", calls[0].get("params") if calls else None, {"city": "Paris"})
    check("complete", done, True)

    print("partial frame is not emitted early")
    partial = zlib.compress(body_frame("hello"))
    wire = chunk(partial[:4]) + b"0\r\n\r\n"
    interceptor = ic.HttpInterceptor(log_dir="/tmp/none")
    result = await interceptor.process_response(wire, "host", "", {})
    check("no half frame", result["body"], "")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
        return 1
    print("PASS: stream decoder")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
