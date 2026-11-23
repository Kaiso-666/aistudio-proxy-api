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
- `CHECK: python3 -m py_compile` on all edited modules → pass; fingerprint and
  validator behaviour exercised directly as pure functions (4 + 8 cases);
  `pyflakes` over non-test code → no undefined names/unused imports/redefinitions.

## Next
1. Run once with `RPC_CAPTURE_LIMIT=1`, then
   `python3 tools/inspect_rpc_capture.py "logs/rpc/*.req" --leaves`.
2. From that tree decide S1-full (in-page tee, per-request routing) vs S3 (direct RPC).
3. Rotation: `rotation_candidate` triggers a *synchronous* summarisation turn inside a
   client request. Speculative handoff (summarise at 0.75x limit, during idle) is the
   next structural win; `apply_rotation` is already idempotent enough to accept a
   precomputed summary.
4. Delete: `ensure_generation_stopped` (dead in production but owned by its unit tests —
   remove both deliberately), MITM child process once RPC mode holds.
