# Optimisation analysis — aistudio-proxy-api

Reasoning only: no code was executed, no browser launched, no benchmark run. Every
claim below is either **derived from the source at the cited line** or explicitly
marked *needs measurement* with the one probe that would settle it.

## Verdict

The proxy is not slow because Gemini is slow. It is slow because **every turn pays a
fixed, serialised browser tax** — prompt entry, panel probes, post-turn button dance,
an artificial inter-stream delay — and because **the browser is used as transport** when
the project has already proven, in its own interceptor, that the wire format is readable
and replayable.

For a chat UI the fixed tax is noise next to 15–20 s of generation. For an agent harness
(OpenCode, Cline, Open WebUI tool loops) it is the whole cost: tool turns generate for
1–3 s and pay the same tax. So the objective is not "faster model", it is
**overhead per turn → ~0** and **overlap of turns**.

Best reachable target:

| | now (code-derived) | after micro work | after RPC mode |
| --- | --- | --- | --- |
| fixed overhead / turn | 1.5–3 s serialised | 0.5–0.8 s | <150 ms |
| TTFB | ~1.5–3 s | same | backend TTFB, 0.3–0.8 s |
| concurrency | 1 (hard) | 1–2 tabs | rate-limit bound |
| RAM | Camoufox (full Firefox) | same | ~120 MB, browser optional |
| runs on Termux/ARM | no | no | yes |

---

## 1. Where the per-turn time actually goes

Default path is the auxiliary stream (`STREAM_PORT=3120`), not DOM polling —
`api_utils/request_processor.py:225-263`. That matters: the completion signal is a gRPC
`done` frame, which is fast. The cost is everything *around* it.

| # | Step | Evidence | Cost |
| --- | --- | --- | --- |
| 1 | `clear_stream_queue()` per request — drains a cross-process queue | `request_processor.py:770-790` | ~ms, but proves routing is global |
| 2 | Model/param cache probes: `_ensure_advanced_settings_expanded` + `_ensure_tools_panel_expanded` on **every** request | `page_controller_modules/parameters.py:60,115,147` | 2–15 DOM round trips |
| 3 | Prompt entry: focus click, `Ctrl+A`, `Delete`, jitter 80–300 ms, then typing or `insert_text`, then readback verify, then `data-value` write | `browser_utils/human_input.py:129-173`, `input.py:168-191` | 0.3–1.5 s |
| 4 | Submit-button enable wait, click | `input.py:201-230` | 0.1–0.5 s |
| 5 | Stream consumption: idle tick `sleep(0.1)` **plus a full-page scroll `evaluate` on every loop iteration** | `api_utils/utils_ext/stream.py:104-127` | ~10 page round trips/s for the whole generation |
| 6 | Completion tail in aux path: on `done` with no body → 10×0.3 s DOM function-call retry; thinking-only → 20×0.5 s DOM wait | `stream.py:313-330`, `stream.py:352-366` | 0–3 s, 0–10 s |
| 7 | Post-turn: `sleep(0.5)`, `is_enabled`, click stop, `to_be_disabled(10 s)` — **before the next request dequeues** | `queue_worker.py:351-372` | 0.6–1.5 s, serialised |
| 8 | Artificial inter-stream delay: consecutive streaming requests held ≥1 s after the previous turn | `queue_worker.py:224-233` | 0.5–1.0 s, serialised |
| 9 | Session bookkeeping: fingerprint whole transcript per turn | `api_utils/chat_sessions.py:199-247` | O(n) Python, small |

Steps 7 and 8 are the ones that hurt twice: they block the **next** client request, not
just the current one. On a 30-step agent loop they cost ~45 s of wall clock that is not
model time.

DOM fallback path (`STREAM_PORT=0`) is worse and should stay a fallback:
`asyncio.sleep(0.5)` poll with 6–8 locator round trips per iteration including two
`check_quota_limit` selectors (`browser_utils/operations.py:39-69,1273`), three
consecutive confirmations (`operations.py:1256`), then extraction with three fixed 0.5 s
sleeps in the copy-button route (`operations.py:1012,1041`).

---

## 2. Structural ceilings, ranked

### S1 — The browser is transport. It does not have to be.

The project already decodes the entire Gemini wire protocol: chunked + zlib +
`GenerateContent` gRPC-web frames (`stream/interceptors.py:138-200`). It already proves
in-process response surgery works, on the model-list endpoint
(`browser_utils/initialization/network.py:15-68`, `context.route("**/*")`).

What it does **not** do: keep the outgoing request body. `HttpInterceptor.process_request`
(`stream/interceptors.py:99-136`) inspects only `jserror` and returns the body untouched.
So the encoder reference is being thrown away every turn — a one-line dump would capture
it.

Consequence: `f.req` (urlencoded protobuf-ish array) + cookies + `at`/`f.sid` is
replayable from `httpx`. The 5 k LOC of selector/typing/panel/scroll machinery exists to
*produce* that body and to *guess* when the answer ended — the wire says both directly.

Ladder:

1. **Capture** (hours, zero risk): write `path`, headers, `f.req` for the first N
   `GenerateContent` calls to `logs/rpc/`. Nothing else.
2. **Encoder** (days): identify the stable array skeleton — model id, `generationConfig`
   (temperature/topP/maxOutputTokens/thinkingConfig/responseSchema/stopSequences), tools,
   `systemInstruction`, `contents[]`. The two opaque tokens refresh from the page
   bootstrap; the browser stays alive only to mint them.
3. **Client** (days): `httpx.AsyncClient(http2=True)` sending the reconstructed body,
   reusing `HttpInterceptor.process_response`'s decoder unchanged. Browser becomes an
   auth/fingerprint front and a fallback, not the request path.

Effects: TTFB → backend; no tabs, no typing, no scroll, no button dance; concurrency
limited only by account rate limits; **runs on this machine** (Termux/ARM cannot host
Camoufox); images become `inlineData` parts instead of a file-upload dialog round trip;
`responseSchema` and native `functionCall`/`functionResponse` parts become available,
which is also the biggest *answer-quality* win available (see §3.7).

Risk / kill criterion: token or anti-abuse drift. Keep `AI_STUDIO_RPC_MODE=dom` as a
one-flag fallback and demote automatically if the RPC path returns 4xx above a threshold
over a rolling window. That is a rate, not a guess — no test needed to design it.

### S2 — One page, one queue, one slot

`STREAM_QUEUE` is a single `multiprocessing.Queue` (`api_utils/server_state.py:51`) and
routing is a single string, `GlobalState.CURRENT_STREAM_REQ_ID`
(`config/global_state.py:62`); `reset_for_new_request` wipes state on each request
(`interceptors.py:76-84`). Two concurrent turns would interleave frames and corrupt both.

So: concurrency is 1 by construction, and a zombie stream aborts the *active* request
(`stream.py:109-118`), while a TTFB timeout **reloads the page** (`stream.py:432-441`) —
which would destroy every other slot's session if slots existed.

Concurrency design that survives rate limits: slots = tabs, each owning its own chat,
stream queue (per-request, not global) and cleanup. Start at 2, grow on clean-turn
windows, shrink to 1 on the first 429/`PERMISSION_DENIED`. Under S3 this is free
(one HTTP/2 client, N streams); under the browser it needs one tab per slot.

Note: `route`-based interception is per-request by nature — one more reason S1's tee
beats the MITM child, which is inherently global. The MITM also costs a child process, a
CA cert, a second port, per-chunk pickling, and a logger that is documented as discarded
(`interceptors.py:60-75`).

### S3 — Session reuse is keyed on a hash of the whole history

`chat_sessions.resolve` requires a **strict prefix** of message fingerprints
(`chat_sessions.py:239,313`) and keys the session on `(model, tools_hash, prefix)`
(`chat_sessions.py:203,213`). Two consequences:

- Any client that rewrites history (compaction, summarisation, system-prompt edit) →
  full replay of the transcript into the UI: O(n) tokens re-sent per turn, O(n²) over a
  loop.
- `tools_hash` in the key means **adding or removing one tool invalidates the session**.
  Agent harnesses change tool sets constantly (MCP servers, per-turn tool availability).
  This is a silent latency cliff.

Best:

- Accept explicit identity: `X-Session-Id` / `conversation_id`, plus
  `previous_response_id` continuation. A client that says "same conversation" is
  authoritative; stop guessing from content.
- No id → longest-common-suffix alignment (`difflib.SequenceMatcher` over fingerprints)
  and submit the divergent tail with a compaction marker, instead of all-or-nothing
  prefix matching.
- Drop `tools_hash` from the key. Tool declarations are request-scoped server state in
  RPC mode; in DOM mode the function-calling cache already tracks declaration changes
  (`utils_ext/function_calling_cache.py`) — double-counting it in the session key only
  destroys good sessions.
- System messages never belong in the fingerprint; they belong in `systemInstruction`,
  which persists across the chat.

### S4 — Rotation is a synchronous, lossy model call inside a client request

At `SESSION_CONTEXT_LIMIT_TOKENS` (default 900 000) the turn becomes: summarise → clear →
reseed with `[CONTEXT HANDOFF]`, paying a full generation on the client's clock.

Best:

- **Speculative handoff**: when `page_tokens > 0.75 × limit`, after the turn's response
  is complete, spend *idle* time producing the summary in a side chat and store it as
  `session.handoff`. Rotation then costs only clear + seed (sub-second), no model call.
- **Never rotate on a `tool` turn** — `force_tool_replay` (`request_processor.py:825`)
  already clears the chat there, so that turn should be the rotation point, at zero cost.
- With S2, rotate into a fresh tab: zero client-visible downtime.
- **Fix the token estimate driving the decision.** `estimate_tokens` is chars/4 + CJK/1.5
  (`utils_ext/tokens.py:4-19`), used both for rotation (`chat_sessions.py:249,346,449`)
  and for reported usage. Code and JSON undercount by roughly 10–25 %, so "900 k" can be
  1.1 M: the backend silently truncates and the agent loses context mid-run — the worst
  failure class because nothing errors. The wire carries `usageMetadata`; use it.

### S5 — Turn tail is serialised into the critical path

`queue_worker.py:351-372` performs `sleep(0.5)` → `is_enabled` → click stop →
`to_be_disabled(10 s)` before dequeuing the next request. In the aux-stream path the
generation has already reported `done`; there is nothing to stop. Gate the block on
"stream did not complete via wire", and reduce it to a single `is_enabled` probe with no
sleep. Combined with removing the ≥1 s artificial inter-stream delay
(`queue_worker.py:224-233`, replace with an adaptive token bucket driven by observed
429/TTFB drift), this is −1.5–2.5 s of *serialised* time per turn.

### S6 — Streaming loop burns a page round trip 10×/s and sniffs text it already has

`stream.py:104-127` re-runs a three-`querySelector` scroll script on **every** loop
iteration, including empty-queue iterations, for the entire generation. AI Studio
auto-scrolls its own transcript; the explicit scroll is defence against a headless
viewport that is usually invisible anyway. Throttle to "content length changed, max 2/s",
or delete it and let `scrollIntoView` on the last turn happen once at `done`.

Similarly, reasoning/body separation and tool-call detection are done by text heuristics
(`TOOL_STRUCTURE_PATTERN`, `boundary_transitions`, accumulator diffing,
`stream.py:16-19,190-260`) when the wire already labels `functionCall` parts and thinking
channels. Keep the heuristics only for emulated mode; on the native path they add latency
and introduce a whole defect class (a model that *writes* XML that looks like a call).

---

## 3. Correctness / compatibility defects that cost quality

Speed is half of "best". These make the proxy a worse *model* than it is:

1. **`max_tokens` is silently dropped.** `ChatCompletionRequest` declares
   `max_output_tokens` and no `max_tokens`/`max_completion_tokens`
   (`models/chat.py:72-89`); Pydantic ignores unknown fields, so every OpenAI client's
   cap is discarded and `DEFAULT_MAX_OUTPUT_TOKENS` wins. Fix with `AliasChoices` and
   enforce it; unbounded output in an agent loop is slower *and* less reliable.
2. **`finish_reason` is never `length`** (`request_processor.py:411,610`). Clients cannot
   distinguish truncation from completion, so a cut answer is treated as final.
3. **Truncated tails poison the session.** DOM-mode stop sequences stop the UI, but
   streamed output clipped by the proxy leaves the remainder in the tab while the client
   believes the turn ended. Any cut must invalidate the session (or `drop_pending`).
4. **Reasoning is concatenated into `content`** in the non-streaming aux path
   (`request_processor.py:403-405`, and the DOM path at `569-571`). Chain-of-thought then
   lives in the transcript the model re-reads next turn, and clients that strip
   reasoning cannot. The streaming path already emits `reasoning_content` deltas
   correctly (`response_generators.py:270`) — the two paths disagree, which is itself a
   bug worth fixing by making the non-stream path match.
5. **Usage is fabricated.** `calculate_usage_stats` (`utils_ext/tokens.py:21-40`)
   concatenates `role: content` and divides by 4. This number is what rotation, profile
   accounting and client-side context management all believe.
6. **Unsupported knobs are ignored rather than rejected**: `n>1`, `logprobs`,
   `presence_penalty`, `frequency_penalty`, `parallel_tool_calls=false`, `seed` (accepted,
   echoed as 0 at `request_processor.py:619`). Silent acceptance is the worst
   compatibility behaviour; return 400 (or implement via RPC `generationConfig`).
7. **`response_format: json_schema` shapes the envelope only.** In RPC mode set
   `responseMimeType: application/json` + `responseSchema`; then tool arguments are
   schema-valid by construction and the emulated-JSON scaffold (and its repair heuristics)
   can be deleted.
8. **Tool results force a fresh chat** (`request_processor.py:819-833`,
   `chat_sessions.force_tool_replay`) — chosen because AI Studio keeps the native turn
   open behind an "Enter function response" widget. Correct today, but it means every
   tool turn re-uploads the transcript. In RPC mode the `functionResponse` part is just
   the next `contents[]` entry: native multi-turn tool use, no replay, no DOM widget.
   This is the single biggest agent-loop win in the whole document.

---

## 4. Micro-optimisations (each a small, reversible diff)

- `operations.py:1273` — replace the 0.5 s poll + 6–8 locator reads with one
  `page.wait_for_function` (stop button absent ∧ input empty ∧ submit disabled), event
  resolution instead of polling; keep a slow fallback tick. Removes both granularity and
  round trips.
- `operations.py:39-69` — quota selectors run every poll iteration; they only matter when
  generation stops or an error overlay appears. Check once, plus once on state change.
- `operations.py:1012,1041` — three fixed 0.5 s sleeps in the copy path. The click already
  resolves when the handler runs; read the clipboard on the next tick. Edit→textarea stays
  first (it already is).
- `response.py:106-134` — `ensure_generation_stopped` sleeps 0.5 s then probes; skip
  entirely when the wire reported `done`.
- `stream.py:313-330,352-366` — the 3 s FC retry and 10 s thinking-only waits run on the
  client's clock. Make them background: emit `done`, resolve the response, then reconcile.
- `stream.py:432-441` — TTFB timeout reloads the page. Under any concurrency this is a
  nuke. Scope the recovery to a fresh tab, never the live page.
- `routers/chat.py:73` — a single 300 s + 120 s deadline per request. With one worker a hung turn
  is a 7-minute outage. Enforce per-phase budgets: submit ≤10 s, TTFB ≤20 s, idle ≤60 s.
- Startup 50–90 s: init is sequential; the geoip pre-flight is already bounded 15 s
  (`FORK-NOTES.md §2.2`). Parallelise model-list fetch + page load + auth inject, and cache
  `last_model_id` in `auth_profiles/metadata.json` to skip the probe on warm restarts.
- `input.py:182-190` — the `data-value` autosize write is one round trip purely for
  layout; skip when the wrapper is not visible.

---

## 5. Sequencing (value × certainty ÷ risk)

Six months of evidence in `FORK-NOTES.md` says this project gets its wins from measured
structural change, not from tuning. Order accordingly:

1. **Day 1 (no risk, no browser needed to reason about):** §4 micro items 1–5, S5 gating,
   §3.1/3.2/3.4/3.5. Everything here is a deletion or a constant; all reversible.
2. **Day 2 (evidence harvest):** dump captured `GenerateContent` request bodies
   (`interceptors.py:99-136`). This single artefact decides between S1-full and S3 — it
   either shows an encoder that is trivially reconstructible or it does not. Do not start
   either path before looking at it.
3. **Week 1–2:** S3 ladder (capture → encoder → httpx client) behind
   `AI_STUDIO_RPC_MODE`, DOM path untouched and default until RPC mode holds on
   consecutive live turns.
4. **Week 2–3:** S3-session identity + speculative rotation + real usage metadata.
5. **Then delete:** MITM child process, DOM function-call parser (1 425 LOC), emulated
   tool scaffold, clipboard extraction, scroll loop, `CURRENT_STREAM_REQ_ID`.

Deliberate non-goal: rewriting the DOM path for concurrency (S2-full). If S3 lands, tab
orchestration is throwaway work; if it does not, S2 is the fallback plan and is only worth
it after the capture in step 2 tells you RPC mode is dead.

---

## 6. What is *not* established here

These are derivations from code, not measurements. Each has a one-line settle:

| claim | cheapest probe |
| --- | --- |
| typing path is 0.3–1.5 s | timestamp `insert_prompt_text` start/end for one turn |
| post-turn dance costs 0.6–1.5 s | timestamp `queue_worker.py:351` → loop top |
| scroll `evaluate` is load, not noise | count calls per turn, then disable and compare turn wall time |
| wire carries `usageMetadata` | grep one captured frame for it |
| `f.req` encoder is reconstructible | read the captured body once |
| rotation is the dominant long-session cost | log rotation count and per-rotation seconds |

## 7. Machine constraint, stated once

This box is Termux/ARM: Camoufox (a glibc Firefox) cannot host here. Every browser-side
item above must be edited here and validated on the Windows host. Only RPC mode (§2 S1)
runs locally — which means, on this machine, the RPC ladder is not just the fastest path,
it is the only path to a self-hosted, self-verifiable proxy.

---

## 8. Status — landed in this pass

Everything below is a deletion, a constant, or an added guard; no control flow was
redesigned, so the failure modes are the ones already in the code.

| Change | File | Effect |
| --- | --- | --- |
| `max_tokens` / `max_completion_tokens` aliased onto `max_output_tokens` | `models/chat.py` | client generation caps are no longer silently dropped |
| reasoning kept out of `content`, surfaced as `reasoning_content` (both paths), thinking-only still returns a non-empty message | `api_utils/request_processor.py` | chain-of-thought stops re-entering the transcript; non-stream/stream now agree |
| inter-stream pacing configurable, default off | `api_utils/queue_worker.py`, `.env.example` | removes ≥1 s of serialised latency per consecutive streaming turn |
| post-turn button dance skipped when the wire already reported `done` | `api_utils/queue_worker.py` | removes 0.5 s + click-and-wait from the critical path before the next request dequeues |
| auto-scroll only when the transcript grew, max 2.5/s | `api_utils/utils_ext/stream.py` | ~10 page round trips/s → ≤2.5 |
| quota probe throttled to 1 per 2 s per page | `browser_utils/operations.py` | 4 round trips/s → 0.5 during the completion poll |
| copy-button fallback: 0.5 s sleeps → 0.1 s | `browser_utils/operations.py` | −1.2 s on the (rare) fallback extraction path |
| `GenerateContent` request bodies captured to `logs/rpc/` | `stream/interceptors.py`, `stream/proxy_server.py` | produces the encoder reference S1/S3 depend on |
| `tools/inspect_rpc_capture.py` | new | decodes a capture offline: rpcid envelope, embedded layers, model id, keys, tree |

Dead code found while editing: `ResponseController.ensure_generation_stopped`
(`browser_utils/page_controller_modules/response.py:106`) has no caller outside its
own tests — 28 lines that can go, and the 0.5 s sleep inside it is unreachable.

Verification: `python3 -m py_compile` on all edited modules passes. Behavioural
verification is deliberately absent — see the preamble.

---

## 9. Status — second pass

The DOM-side counterpart of the RPC argument: if a turn is going to reuse a loaded
chat, the decision must not be thrown away by bookkeeping.

| Change | Why |
| --- | --- |
| tool-call ids and `type` excluded from message fingerprints; arguments canonicalised (sorted keys, compact separators); CRLF folded into LF | an adapter that re-serialises its own history (or renumbers call ids) used to fail the prefix test and force a full transcript replay — the O(n²) path `chat_sessions` exists to prevent |
| tool set removed from the session key (`SESSION_KEY_INCLUDE_TOOLS=false`, opt-in to restore) | any per-turn change to the tool list created a new key and a full replay; declarations are re-applied per request and the function-calling cache already invalidates on change, so the page cannot inherit stale tools |
| `tools_changed` carried on `Resolution` and logged in the session line | a silent declaration switch was indistinguishable from a normal reuse |
| `n`, `logprobs`, `top_logprobs`, `presence_penalty`, `frequency_penalty` accepted by the model and **rejected** with 400 when set | pydantic was dropping them, so clients got a 200 for a request the transport did not perform; `parallel_tool_calls=false` is rejected for the same reason |

Checks actually exercised (pure functions, no proxy): fingerprint stability under
call-id and argument-order churn, divergence still detected on a value change,
CRLF folding, key stability across tool sets, and the eight validator cases
(`n=1` and `presence_penalty=0` pass; `n=3`, `logprobs`, `top_logprobs`,
`presence_penalty=0.5`, `frequency_penalty=1.2`, `parallel_tool_calls=false` reject).

---

## 10. Status — third pass

Two liveness/back-pressure gaps that only show up under a real agent loop, where
turns are short and frequent and the client has its own timeouts.

| Change | Why |
| --- | --- |
| SSE comment frame (`: keepalive`) every 10 s of stream silence, streaming path only (`enable_keepalive` defaults False elsewhere) | a thinking phase can be silent for a minute; an empty body that long is indistinguishable from a dead connection, and any client or intermediary with a 30–60 s read timeout drops the turn. Comment frames are invisible to every SSE parser, so no chunk contract changes |
| `MAX_QUEUE_DEPTH` admission control (default 3, 0 disables) → 429 + `Retry-After` before enqueue | the worker serialises to one browser context; a deep queue converts a fast retryable signal into a multi-minute stall whose client has already given up |

Deliberately **not** added:

- a role-only opening chunk. It is the OpenAI shape, but the current stream
  already works with the target clients, and inserting a leading frame changes the
  chunk contract for no measured gain — the existing generator tests assert the
  first chunk is the first content delta, and they stay valid.
- a stale-queue drop inside the worker. A request whose client vanished is
  already rejected at dequeue by `_test_client_connection` (499), so an extra
  age-based policy would only add a second, conflicting rule for the case where
  the client is still there and merely patient.

---

## 11. Status — fourth pass: static analysis over runtime guessing

With no browser available, the honest way to find defects is a checker rather than
more speculation. `pyflakes` over every non-test module: **no undefined names, no
unused imports, no redefinitions**. Two real findings, one of them a silent
correctness bug.

### 11.1 A failed model switch poisons the next page load

`switch_ai_studio_model` writes `localStorage.aiStudioUserPreference.promptModel`
*before* navigating and verifying. Every failure path then returned `False`
without undoing it:

- page displayed a different model than requested,
- AI Studio refused the localStorage change,
- any exception during the switch.

The caller restores `state.current_ai_studio_model_id` (`request_processor.py`,
`_handle_model_switch_failure`), but storage now disagrees with that state. The
next page load boots into the new model; the next request compares against the
restored state, concludes "already at target", skips the switch and generates
with the **wrong model** — with no error anywhere. The fossil of the intended fix
was a dead local, `_original_prompt_model`, which pyflakes flagged.

Now: `prefs_modified` tracks whether storage was touched, and all three failure
paths call `_restore_previous_prefs(reason)`, which rewrites the original
snapshot and logs what it restored and why. Cancellation is excluded on purpose —
restoring during teardown can hang.

### 11.2 Dead state that implied missing checks

- `stream.py`: `_data_received` was set but never read; the actual TTFB guard is
  `received_items_count == 0`. Removed, so the next reader is not misled into
  thinking a second gate exists.
- `operations.py`: `_timeout_ms` was computed and dropped (the loop uses
  `current_timeout_seconds`), and two vestigial `state` reads existed only to
  silence themselves with `# noqa`. Removed.
- `tools/inspect_chat.py` wrote artifacts to `C:\Users\meow\...` — a path from the
  author's box that silently fails on every other machine, including the one
  likely to debug the next upstream UI change. Now `tempfile.gettempdir()/aistudio-inspect`.

Reproduce:

```
python3 -m pyflakes $(git ls-files '*.py' | grep -v '^tests/' | grep -v '^config/__init__.py')
# remaining output is only "`global X` is unused" (mutation-only pattern) - no defects
```

---

## 12. Status — fifth pass: make §6 measurable

Every remaining claim in this document is gated on one live run, and until now
nothing in the codebase produced the numbers. `api_utils/turn_timing.py` does,
behind `TURN_TIMING=1`, at five mark points that already existed as natural
boundaries:

| phase | marked at | answers |
| --- | --- | --- |
| `enqueue` → `dequeued` | handler entry → worker pickup | §1 step 8, admission control tuning |
| `dequeued` → `submitted` | worker → prompt submitted | §1 steps 2–4: panel probes, prompt entry |
| `submitted` → `first_byte` | submit → first stream item | TTFB, the number that decides RPC-vs-DOM urgency |
| `first_byte` → `done` | first item → response complete | model time, i.e. the denominator for "overhead" |
| `done` → `finish` | complete → post-turn work done | §1 steps 7 and the rotation cost |

Design constraints, all deliberate:

- `time.monotonic()`, so a clock jump cannot invent a negative phase.
- Any phase may be missing (non-streaming has no TTFB); deltas appear only when
  both ends exist, so the record is never a lie-by-zero.
- The ring buffer (last 20) is always kept: `/health` reports phase medians even
  when logging is off, so an incident does not require having predicted it.
- `mark()` without `begin()` is tolerated and bounded (64 tracked turns), because
  a cancelled or requeued turn can outlive its handler.
- Nothing in the request path reads the numbers; a broken timing module cannot
  fail a turn.

With this, the §6 table stops being a guess: one capture run also yields the
per-phase split, and any change in this document can be judged against the
median rather than against the anecdote that motivated it.

---

## 13. Status — sixth pass: structured output stops being a lie

`response_format` was parsed, echoed back inside the response object
(`response_payloads.py:37`), and otherwise ignored. That is worse than refusing
it: the client sees its own request reflected in the reply and has every reason
to believe the schema was applied. A non-streaming `json_schema` caller then
gets prose, or gets JSON it never validated.

There is no grammar-constrained decoding available — AI Studio's page cannot be
told to decode against a schema — so the honest maximum is *instruction plus
normalisation*:

| step | where | effect |
| --- | --- | --- |
| prepend a `[RESPONSE FORMAT]` block, schema included, for `json_object` / `json_schema` | `utils_ext/prompts.py:build_structured_output_instruction`, prepended in `prepare_combined_prompt` | the model is actually told, including on tail-only (delta) submissions |
| unwrap a whole-response ```json fence | `utils_ext/string_utils.py:strip_json_code_fence`, applied on both non-streaming paths | models fence JSON anyway; a strict parser then rejects a correct answer |
| leave the streaming path alone | — | a fence already flushed cannot be retracted; buffering the head to detect one would add latency to every JSON stream, which is a worse trade than the fence itself |

Deliberately not done: schema *validation* with a 400 on mismatch. Turning a
soft failure into a hard one mid-agent-run costs the turn; the client already
has the schema and is the right place to judge.

Verified directly (pure functions, 6 fence cases): fenced JSON with and without
a language tag unwraps; prose containing a fence, a `python` fence, plain JSON
and an unclosed fence are all returned untouched.

---

## 14. Status — seventh pass: truncation was being reported as completion

Three defects with one root cause: the stream dict uses `reason` for two
different things — reasoning *text* in data frames, and a status token
(`silence_detected`, `internal_timeout`, `hard_timeout`, `ttfb_timeout`,
`zombie_stream_aborted`) in control frames.

1. **Internal status strings leaked into `reasoning_content`.** The SSE
   generator assigned `reason` straight into the reasoning latch, so a timeout
   could emit `delta.reasoning_content: "silence_detected"` as if the model had
   thought it.
2. **A truncated turn was reported as `finish_reason: "stop"`.** An agent reading
   that believes the cut text is a complete answer and keeps going on it. The
   streaming path now maps every control stop to `finish_reason: "length"` and
   logs which one; the non-streaming path raises for *any* control stop instead
   of only `internal_timeout` (502 kept, so the existing contract and its test
   stay valid).
3. **The synthetic "model finished thinking but generated no output" message was
   injected on truncation.** It turns "we lost the stream" into "the model chose
   to say nothing" — the same class of lie. Suppressed when a control stop is
   known.

And the trigger itself was wrong in the common case: silence detection fired
after `silence_threshold` (60 s default) **without asking the page**, so a
high-thinking model that was quietly reasoning had its live generation aborted
and the partial answer returned. The UI-active probe already existed — it was
just evaluated after the abort. It now runs first (one locator probe per
threshold, not per tick), resets the silence clock when generation is alive, and
only then declares silence.

Judgement call, stated: `length` for a transport-side truncation is the
least-wrong standard value — it tells the client "this is cut", which is true,
where `stop` tells it the opposite. A client that retries on `length` will redo
the turn; a client that trusts `stop` will reason on half an answer.

---

## 15. Status — eighth pass: tool turns, the fake DOM stream, and truncated DOM answers

Four defects, all on paths that only a real loop exercises.

### 15.1 Every function-call turn paid two seconds of dead time

`gen_sse_from_aux_stream` guards an "empty answer might be a quota wall" probe
with `done and not has_started_body and not recovering and not quota`. A native
tool-call turn legitimately carries **no body text** — it is all in `function` —
so every tool call ran a quota probe and then `await asyncio.sleep(2.0)` before
finalising. Twenty tool calls, forty seconds of sleep, no content behind it.
Guard extended with `and not function`: an empty *text* answer still gets the
probe, an empty-and-callable turn no longer does.

### 15.2 The DOM "stream" was collect-then-replay at 166 characters/second

`gen_sse_from_playwright` waits for the complete answer (`get_response_with_
function_calls`), then emits it in 5-character chunks with `sleep(0.03)` — a
3 kB answer became ~600 chunks and **~18 seconds of artificial replay** on top of
the generation it had already waited for. Now 512-character blocks with no
pacing: the content already exists, and chunking was only ever about write size.

Note what this does *not* fix: this path still has TTFB = full generation time.
Real incremental streaming on the DOM path needs per-tick text polling, which is
a different (and unverifiable-here) change. The aux path is the streaming path;
this one is a fallback and now at least stops adding latency to itself.

### 15.3 The DOM path computed "did it finish?" and threw the answer away

`ResponseController.get_response` already calls `_wait_for_response_completion`
and gets a boolean, then returns only the text. A poll timeout therefore produced
`finish_reason: "stop"` on a partial answer — the same lie fixed for the aux path
in §14, still live on the fallback.

`completion_detected` is now recorded on the controller, copied into both result
dicts as `truncated`, and consumed:

- non-streaming: `finish_reason: "length"` plus a warning;
- streaming DOM: the stop chunk reports `length`;
- both invalidate the session.

### 15.4 A truncated turn must not keep its session

If the client received less than the page holds, the page transcript is no longer
the transcript the client will send back. The next delta would submit the
client's truncated copy of a reply the model already has in full. Both transports
now invalidate the session on a truncating stop, so the next turn replays into a
cleared chat.

`zombie_stream_aborted` is deliberately excluded from that set: it means *another*
request has taken the page over, and invalidating the active session would
destroy its successor. It still reports `finish_reason: "length"` to its own
client, because that client's answer really was cut.

---

## 16. Status — ninth pass: the decoder was re-emitting every prefix on every read

The MITM child receives the response body **cumulatively** and hands the whole
accumulated body to `process_response` on every read. That function decoded it
statelessly and then did `self.response_buffer += decoded_str` — so each read
re-appended the entire plaintext produced so far. Measured with a four-frame
body fed in six-byte cumulative reads, the client-visible emission was:

```
The | The | quick | quick | quick brown | quick brown | quick brown fox | The quick brown fox
```

which is both duplicated and out of order. Everything downstream ("`use_stream_
response` normalises to a cumulative body, then `last_body_pos` turns it into
deltas") was compensating for a decoder that never had a cursor. Fixed with one
field: `_response_plain_len`, the length of the full decoded text already handed
to the buffer; only `decoded[len:]` is appended. A shorter decode means a new
response started without `reset_for_new_request`, so the buffer rebases instead
of emitting a prefix as if it were a continuation.

Three more wire-level failures found by the same harness, each of which was a
*silent total loss* rather than a degradation:

| case | old behaviour | now |
| --- | --- | --- |
| chunk extension `1a;name=value` | `int(...,16)` raises, loop breaks, **every frame of the response is dropped** | extension stripped, chunk decoded |
| trailers after the terminal chunk (normal gRPC-web: `0\r\n` + `grpc-status: 0\r\n\r\n`) | `done` never true; the finished stream was ended by the 60 s silence detector and reported as a truncation | the zero-length chunk ends the message; trailers are irrelevant |
| identity (non-gzip) body | `zlib.decompressobj` returns `b""` for input that is not a compressed stream: **the whole answer disappears** and only a timeout reports it | gzip/zlib magic is checked first; anything else passes through as plain text |
| a multi-byte character split across two reads | `UnicodeDecodeError` returned an empty result for that read *and* left the buffer untouched, so the next cumulative read re-appended the whole prefix | decode with `errors="ignore"`: the dropped tail character reappears in the next (cumulative) decode and the cursor keeps the boundary |

The proxy loop no longer decides a response is over by searching for a literal
`0\r\n\r\n` in its buffer (which never appears when trailers are present, so the
buffer grew for the life of the connection). It clears on the interceptor's
`done`.

Two test expectations encoded the old behaviour and were corrected with reasons
in place: `done=False` for a body that is not compressed, and `done=False` for a
lone zero-length chunk. Both were the *defect*, not a specification.

`tools/check_stream_decoder.py` is the standing regression: it stubs the
module's imports, replays bodies in cumulative one-byte reads, and asserts exact
text for gzip, identity, extensions, trailers, reasoning/body interleaving, a
function-call frame and a split multi-byte character. It needs no project
dependencies, which matters because this module is the one the rest of the proxy
trusts to be lossless.

---

## 17. Status — tenth pass: a config knob that did the opposite, and a DOM probe on every turn

### 17.1 `CAMOUFOX_HUMANIZE=0` made typing slower, and disabled nothing

`human_input.py` read its own `CAMOUFOX_HUMANIZE` flag to choose the per-key
delay:

```python
humanize = _env_flag("CAMOUFOX_HUMANIZE", True)
delay = 0 if humanize else random.randint(25, 60)
```

But Camoufox's humanisation is configured in `launch_camoufox.py`, which sets
`"humanize": _env_float("CAMOUFOX_HUMANIZE_MAX_TIME", 0.55)` — a float, always
on. Nothing in the launch path reads `CAMOUFOX_HUMANIZE`, so setting it to 0
did **not** turn humanisation off; it only stacked 25-60 ms of our own sleep on
top of the browser's cadence, for up to 320 characters. `FORK-NOTES.md` prices
Camoufox typing at ~157 ms/char, so the "fast" setting added seconds per turn
and the flag's name promised the opposite of its effect.

The knob is gone; `delay=0` is unconditional and the comment names the real one
(`CAMOUFOX_HUMANIZE_MAX_TIME`). Default behaviour is unchanged — this only
removes a trap.

Same class as §15.1 and §16: a switch that appears to control something it does
not reach. Reading where a value is *consumed*, not where it is read, is what
finds these.

### 17.2 A DOM scan ran on every completed text turn

On the `done` packet, before the final chunk was yielded, the consumer probed
the page for function calls:

```python
if done and not has_seen_functions and page:
    for _ in range(10):
        dom_functions, dom_text = await detect_function_calls_from_dom(...)
        if dom_functions: break
        if accumulated_body: break          # <-- the intent
        await asyncio.sleep(0.3)
```

The `break` says the probe is only meaningful when the wire produced no text,
but the *first* probe ran unconditionally — one DOM parse (and its locator
round-trips) on the critical path of every completed turn, text or not.

The guard is now on the outer `if`. Nothing is lost: a text-format tool call is
inside the body and is already parsed from it, and the case the fallback exists
for (an empty body, where the page may hold an answer or a rendered call) still
probes, still retries, and still injects `dom_text`.

Cost removed: one DOM parse per turn. Cost added: none.
