# NOTES — aistudio-proxy-api optimisation

## Goal
Make the fork the best agent backend it can be: overhead per turn → ~0, turns
overlappable, correct OpenAI surface, runnable without a browser.

## State
- Repo at `~/aistudio-proxy-api` (fork `Kaiso-666/aistudio-proxy-api`, base `b5d3c39`).
- Analysis: `OPTIMIZATION.md` (reasoning only, no proxy run). §8 lists what landed.
- Machine is Termux/ARM → Camoufox cannot host here. Browser-side work is edit-here,
  validate-on-Windows; RPC mode is the only path that runs locally.

## Landed (local commit)
- `models/chat.py`: `max_tokens` / `max_completion_tokens` alias → `max_output_tokens`.
- `api_utils/request_processor.py`: reasoning split from `content` on both paths.
- `api_utils/queue_worker.py`: inter-stream pacing opt-in (`STREAM_INTERSTREAM_DELAY_S`,
  default 0); post-turn button dance skipped when the wire already said `done`.
- `api_utils/utils_ext/stream.py`: auto-scroll only on growth, ≤2.5/s.
- `browser_utils/operations.py`: quota probe throttled to 2 s; copy-path sleeps 0.5→0.1.
- `stream/interceptors.py` + `stream/proxy_server.py`: capture `GenerateContent` request
  bodies to `logs/rpc/` (`RPC_CAPTURE_LIMIT`, default 25, 0 disables).
- `tools/inspect_rpc_capture.py`: offline capture decoder (validated on a synthetic body).
- `api_utils/chat_sessions.py`: fingerprints ignore tool-call ids/type and canonicalise
  arguments; tool set out of the session key (`SESSION_KEY_INCLUDE_TOOLS` to restore);
  `tools_changed` surfaced in the session log line.
- `models/chat.py` + `utils_ext/validation.py`: `n`/`logprobs`/`top_logprobs`/
  `presence_penalty`/`frequency_penalty` now 400 instead of being silently dropped.
- `api_utils/utils_ext/stream.py` + `response_generators.py`: SSE comment keepalive
  (`: keepalive`) every 10 s of silence, streaming path only.
- `api_utils/routers/chat.py`: `MAX_QUEUE_DEPTH` admission control → 429 + Retry-After.
- `browser_utils/models/switcher.py`: a failed model switch left
  `localStorage.promptModel` on the new model → next page load booted into a model
  `state` did not believe in → later requests skipped switching and generated with
  the wrong model, silently. All three failure paths now restore the snapshot.
- `api_utils/turn_timing.py`: per-turn phase timing (queue / prep / TTFB / gen / tail),
  `TURN_TIMING=1` for a log line, medians always on `/health`.
- `response_format`: was parsed, echoed in the response and ignored. Now translated
  into a `[RESPONSE FORMAT]` instruction at the top of the prompt, and a whole-response
  fence is unwrapped on the non-streaming paths. Instructed, not enforced.
- truncation: silence detection now asks the page before aborting a live generation;
  control stops no longer leak into `reasoning_content`; a cut turn reports
  `finish_reason=length` instead of `stop`, and the non-streaming path raises 502 for
  every control stop, not just `internal_timeout`. The DOM fallback now propagates its
  completion flag too (`truncated`), and both transports invalidate the session on a
  truncating stop.
- tool turns: the 2s quota-probe sleep no longer runs when a turn carries function
  calls (it was costing 2s per tool call in an agent loop).
- DOM "streaming" no longer paces a finished answer at 5 chars/30ms (~18s per 3kB).
- stream decoder: `process_response` re-appended the whole decoded plaintext on every
  cumulative read, so text was duplicated and reordered; it now keeps a plaintext
  cursor (`_response_plain_len`). Chunk extensions, trailer-terminated streams,
  identity (non-gzip) bodies and split multi-byte characters no longer lose the
  response. Regression check: `python3 tools/check_stream_decoder.py`.
- `CAMOUFOX_HUMANIZE` in `human_input.py` did not reach the launch path (which
  always humanises); setting it to 0 only added 25-60ms per typed character on
  top of Camoufox's cadence. Removed; `CAMOUFOX_HUMANIZE_MAX_TIME` is the real knob.
- the per-turn DOM function-call probe now only runs when the wire produced no body
  (its retry loop already stopped on that condition).
- `CHECK: python3 -m py_compile` on all edited modules → pass; fingerprint, validator
  and turn_timing behaviour exercised directly as pure functions (4 + 8 + 8 cases);
  `pyflakes` over non-test code → no undefined names/unused imports/redefinitions.
- `RUNTIME_MODE` (default `standard`): `termux` = attach mode, no local Camoufox.
  `launch_camoufox.py --termux [--browser-endpoint http://127.0.0.1:9222]` selects it
  for one run; `auto` opts into Termux detection. `config/runtime_mode.py` resolves the
  mode, the endpoint (`BROWSER_CDP_ENDPOINT` / `BROWSER_WS_ENDPOINT` /
  `CAMOUFOX_WS_ENDPOINT`) and the connector (`chromium.connect_over_cdp` for http
  endpoints, `firefox.connect` otherwise). Attach mode defaults `STREAM_PORT=0` (the
  MITM only sees a browser routed through it), probes `/json/version` before startup,
  and reports itself in `/health` as `runtime.mode` / `runtime.browser.*`.
  CHECK: `python3 -c "import config.runtime_mode"`; mode/endpoint/kind matrix exercised
  directly (11 cases); `/json/version` probe exercised against a stub server and a
  closed port; `tests/config/test_runtime_mode.py` for the suite.
  Unverified: no real browser was attached — the CDP connect path and the attach
  launch both need a live Chromium.
- prompt assembly: every system/developer message is kept (only the first used to
  survive a `break`), `developer` is treated as a system role, and `---` separators
  are only emitted for turns that actually render (no more `---\n\n---`, and no
  double separator after the tool catalogue).
  CHECK: shapes exercised directly with stub imports (4 cases); the old
  "System 2 should be skipped" test assertion was inverted with its rationale.

## Next
1. One live run with `RPC_CAPTURE_LIMIT=1 TURN_TIMING=1`: the capture decides S1 vs S3,
   the timing line replaces the estimates in `OPTIMIZATION.md` §6. Then
   `python3 tools/inspect_rpc_capture.py "logs/rpc/*.req" --leaves`.
2. From that tree decide S1-full (in-page tee, per-request routing) vs S3 (direct RPC).
3. Rotation: `rotation_candidate` triggers a *synchronous* summarisation turn inside a
   client request. Speculative handoff (summarise at 0.75x limit, during idle) is the
   next structural win; `apply_rotation` is already idempotent enough to accept a
   precomputed summary.
4. Delete: `ensure_generation_stopped` (dead in production but owned by its unit tests —
   remove both deliberately), MITM child process once RPC mode holds.
