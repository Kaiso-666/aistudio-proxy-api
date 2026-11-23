#!/usr/bin/env python3
"""
Inspect captured AI Studio `GenerateContent` requests.

Why this exists
---------------
The whole "stop using the browser as transport" plan (OPTIMIZATION.md, S1/S3)
turns on one question: is the outgoing `f.req` body reconstructible from a
template plus a handful of tokens? That question is answered by looking at the
raw body, not by reasoning about it. `stream/interceptors.py` now persists those
bodies to `logs/rpc/*.req` (bounded, opt-out via `RPC_CAPTURE_LIMIT=0`).

This tool turns a capture into the shape the encoder needs:

  * the outer batchexecute envelope (rpcid, request payload, generic),
  * every embedded JSON layer, with its indices,
  * which indices carry the model id, the generation config, the tools and the
    conversation contents,
  * the companion form fields (`at`, `bl`, `f.sid`, `_reqid`, `rt`), which are
    the values that have to be refreshed from the page.

Usage
-----
    python tools/inspect_rpc_capture.py logs/rpc/*.req
    python tools/inspect_rpc_capture.py logs/rpc/20260101-101500-001.req --json
    python tools/inspect_rpc_capture.py logs/rpc/*.req --leaves

No project imports: it must run on a bare interpreter, including a phone.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple
from urllib.parse import unquote_plus

MAX_PREVIEW = 96
EMBEDDED_JSON_MIN = 8

# Fields Gemini's web client sends alongside f.req. Values are session-scoped
# credentials or counters; the encoder has to source them at runtime.
KNOWN_FORM_FIELDS = ("at", "bl", "f.sid", "_reqid", "rt", "hl", "source-path")

MODEL_HINT = re.compile(r"^(?:models/)?(?:gemini|gemma|learnlm)[a-z0-9._/-]*$", re.I)
RPC_ID_HINT = re.compile(r"^[A-Za-z0-9_]{6,}$")


def _preview(value: Any, limit: int = MAX_PREVIEW) -> str:
    if isinstance(value, str):
        flat = value.replace("\n", "\\n")
        return flat if len(flat) <= limit else flat[: limit - 1] + "…"
    return repr(value)


def _try_json(text: str) -> Optional[Any]:
    if len(text) < EMBEDDED_JSON_MIN:
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None


def parse_body(raw: bytes) -> Tuple[str, List[Tuple[str, str]]]:
    """Split a captured body into its request line and form fields."""
    text = raw.decode("utf-8", errors="replace")
    line = ""
    if text.startswith("POST "):
        split = text.find("\n")
        if split == -1:
            return text.strip(), []
        line = text[:split].strip()
        text = text[split + 1 :]

    fields: List[Tuple[str, str]] = []
    # The body is form-encoded; `f.req` carries %-encoded JSON and the rest are
    # short scalars. Split on & only - nothing upstream escapes it in values.
    for part in text.split("&"):
        if not part:
            continue
        if "=" not in part:
            fields.append((part, ""))
            continue
        key, _, value = part.partition("=")
        fields.append((unquote_plus(key), unquote_plus(value)))
    return line, fields


def walk(value: Any, path: str = "$", depth: int = 0, out: Optional[List[str]] = None) -> List[str]:
    """Render a compact tree, decoding embedded JSON strings one level down."""
    if out is None:
        out = []
    pad = "  " * depth
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(item, (dict, list)):
                out.append(f"{pad}{key}: {type(item).__name__}[{len(item)}]")
                walk(item, child, depth + 1, out)
            else:
                out.append(f"{pad}{key}: {_preview(item)}")
        return out
    if isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            if isinstance(item, (dict, list)):
                out.append(f"{pad}[{index}]: {type(item).__name__}[{len(item)}]")
                walk(item, child, depth + 1, out)
                continue
            embedded = _try_json(item) if isinstance(item, str) else None
            if embedded is not None:
                out.append(f"{pad}[{index}]: <embedded json {type(embedded).__name__}>")
                walk(embedded, child, depth + 1, out)
            else:
                out.append(f"{pad}[{index}]: {_preview(item)}")
        return out
    out.append(f"{pad}{_preview(value)}")
    return out


def collect_leaves(value: Any, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from collect_leaves(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from collect_leaves(item, f"{path}[{index}]")
    elif isinstance(value, str):
        embedded = _try_json(value)
        if embedded is not None:
            yield from collect_leaves(embedded, f"{path}<json>")
        else:
            yield path, value


def summarise(fields: List[Tuple[str, str]]) -> dict:
    summary: dict = {
        "form_fields": {},
        "rpc": None,
        "layers": 0,
        "model_candidates": [],
        "key_candidates": [],
        "f_req_bytes": 0,
    }
    freq = None
    for key, value in fields:
        if key == "f.req":
            freq = value
            summary["f_req_bytes"] = len(value)
        else:
            summary["form_fields"][key] = _preview(value, 24)

    if freq is None:
        return summary

    payload = _try_json(freq)
    if payload is None:
        summary["rpc"] = {"note": "f.req is not plain JSON after url-decode"}
        return summary

    # batchexecute envelope: [[[rpcid, payload_json_string, null, "generic"]]]
    try:
        inner = payload[0][0]
        if isinstance(inner, list) and len(inner) >= 2:
            summary["rpc"] = {
                "rpcid": inner[0] if isinstance(inner[0], str) else None,
                "has_payload_string": isinstance(inner[1], str),
                "tail": [_preview(item, 20) for item in inner[2:]],
            }
    except (IndexError, TypeError):
        summary["rpc"] = None

    layers = 0
    models: List[str] = []
    keys: List[str] = []

    def scan(item: Any) -> None:
        nonlocal layers
        if isinstance(item, dict):
            for key, child in item.items():
                keys.append(key)
                scan(child)
        elif isinstance(item, list):
            for child in item:
                scan(child)
        elif isinstance(item, str):
            if MODEL_HINT.match(item.strip()):
                models.append(item.strip())
            embedded = _try_json(item)
            if embedded is not None:
                layers += 1
                scan(embedded)

    scan(payload)
    summary["layers"] = layers
    seen: set = set()
    for model in models:
        if model not in seen:
            seen.add(model)
            summary["model_candidates"].append(model)
    seen_keys: set = set()
    for key in keys:
        if key not in seen_keys:
            seen_keys.add(key)
            summary["key_candidates"].append(key)
    summary["key_candidates"] = summary["key_candidates"][:80]
    return summary


def report(path: Path, as_json: bool, leaves: bool) -> None:
    raw = path.read_bytes()
    line, fields = parse_body(raw)
    summary = summarise(fields)

    if as_json:
        print(json.dumps({"file": str(path), "request_line": line, **summary}, indent=2))
        return

    print(f"\n=== {path} ({len(raw)} bytes) ===")
    if line:
        print(f"request: {line[:200]}")
    if not fields:
        print("body: no form fields decoded")
        return

    printed = {key for key, _ in fields}
    missing = [name for name in KNOWN_FORM_FIELDS if name not in printed]
    print(f"form fields: {', '.join(sorted(printed))}")
    if missing:
        print(f"absent: {', '.join(missing)}")

    freq = next((value for key, value in fields if key == "f.req"), None)
    if freq is None:
        print("no f.req field; nothing to decode")
        return

    payload = _try_json(freq)
    if payload is None:
        print(f"f.req ({len(freq)} chars) is not JSON after url-decode; head:")
        print("  " + freq[:400])
        return

    print(f"f.req: JSON, {len(freq)} chars, {summary['layers']} embedded layer(s)")
    if summary["rpc"]:
        print(
            "rpc envelope: rpcid={rpcid} payload_is_string={has_payload_string} tail={tail}".format(
                **summary["rpc"]
            )
        )
    if summary["model_candidates"]:
        print(f"model id candidates: {', '.join(summary['model_candidates'])}")
    if summary["key_candidates"]:
        print(f"object keys: {', '.join(summary['key_candidates'][:20])}")

    print("--- tree ---")
    print("\n".join(walk(payload)))

    if leaves:
        print("--- string leaves ---")
        for leaf_path, value in collect_leaves(payload):
            if value.strip():
                print(f"{leaf_path} = {_preview(value)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("paths", nargs="+", help="captured .req files")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    parser.add_argument("--leaves", action="store_true", help="list every string leaf")
    args = parser.parse_args()

    seen_any = False
    for pattern in args.paths:
        matches = glob.glob(pattern) if any(ch in pattern for ch in "*?[") else [pattern]
        for match in sorted(matches):
            path = Path(match)
            if not path.is_file():
                print(f"skip (not a file): {path}", file=sys.stderr)
                continue
            seen_any = True
            try:
                report(path, args.json, args.leaves)
            except Exception as exc:  # a malformed capture must not stop the batch
                print(f"{path}: unreadable ({exc})", file=sys.stderr)
    if not seen_any:
        print("no capture files matched", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
