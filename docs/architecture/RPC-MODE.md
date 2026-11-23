# RPC mode — design note

Status: proposed. Nothing here is implemented. It exists so the work in
`OPTIMIZATION.md` §2 (S1/S3) can be executed without re-deriving the decisions,
and so the parts that are *not* safe to guess are named explicitly.

## Goal

Serve `/v1/chat/completions` from a plain HTTPS client against AI Studio's own
RPC endpoint, with the browser demoted to a credential source and a fallback.

Non-goals: replacing the DOM path in one step; supporting multiple accounts; any
change to the OpenAI surface.

## Key decision: mutate a captured template, do not reconstruct the encoder

`f.req` is a nested array whose middle layers are protobuf-shaped by convention,
not by schema. Reconstructing it from first principles means guessing dozens of
positional slots whose meaning is only observable, and every guess is a silent
wrong-answer bug (a temperature that lands in the wrong index still returns 200).

Instead:

1. Capture one working `GenerateContent` request (`RPC_CAPTURE_LIMIT=1`).
2. Keep that body as a **template** on disk (`auth_profiles/rpc_template.req`).
3. On each turn, parse it, replace only the slots that change
   (`contents`, `systemInstruction`, `generationConfig`, `tools`,
   `toolConfig`), and re-encode.
4. Everything not understood is preserved byte-for-byte from the template,
   including fields nobody has named yet.

Cost: the template is model- and build-specific, so it is re-captured when
`bl` (build label) changes. Benefit: an unknown field cannot corrupt a request —
it is passed through from a request the browser itself issued.

## Message flow

```
client ── POST /v1/chat/completions ──► FastAPI
                                        │
                        ┌───────────────┴────────────────┐
                        │ RPC_MODE=rpc                   │ RPC_MODE=dom
                        ▼                                ▼
              rpc_client.send(turns)              (today's queue worker)
                        │                                │
       cookies + at + bl + f.sid from profile      Playwright + page
                        │                                │
                https://aistudio.google.com/…/GenerateContent
                        │
              reuse HttpInterceptor.process_response
              (chunked → zlib → frame grammar)
                        │
              map frames → SSE deltas (text / reasoning / functionCall)
```

## Credentials and their sources

| value | source | lifetime | refresh |
| --- | --- | --- | --- |
| cookies (`__Secure-1PSID`, …) | saved auth profile JSON | days–weeks | existing cookie-refresh path |
| `at` | page bootstrap (same place the app's RPC helper reads it) | minutes–hours | `page.evaluate` on the live tab, or the next captured request |
| `bl` | bootstrap | until Google ships a build | re-capture on 4xx |
| `f.sid` | bootstrap | session | with `at` |
| `_reqid` | client-side counter | per request | `+= 100000` |

`at` is the only value that decays fast, and it is exactly what the live tab is
for. The browser therefore stays open, idle, and cheap; it is not on the request
path.

## Request mapping

| OpenAI field | slot |
| --- | --- |
| `messages[]` (user/assistant) | `contents[]` (`role: user`, `role: model`) |
| `messages[0].role == system` | `systemInstruction` |
| `tools[]` | `tools[].functionDeclarations[]` |
| assistant `tool_calls[]` | `contents[].parts[].functionCall` |
| `role: tool` | `contents[].parts[].functionResponse` (by `id`) |
| `temperature`, `top_p`, `stop`, `max_tokens` | `generationConfig` |
| `response_format.json_schema` | `responseMimeType` + `responseSchema` |
| `reasoning_effort` | `thinkingConfig.thinkingBudget` |
| `seed` | `generationConfig.seed` if the template has the slot |

Anything in this table that the template does not contain is a **stop** — return
a 400 for that request and log the missing slot. Never silently ignore, which is
the current behaviour for `max_tokens`, `n`, and penalties.

## Response mapping

Reuse `HttpInterceptor.process_response` unchanged: it already turns chunked +
zlib frames into `{reason, body, function, done}`. The RPC client differs only in
who feeds it. That means the frame grammar, the reasoning/body split and the
function-call accumulation logic are shared with the DOM path instead of being
duplicated — one place to fix, both transports benefit.

Two things the wire can now do that the DOM cannot:

- `usageMetadata` → real `prompt_tokens` / `candidates_tokens`. Feeds rotation and
  per-profile accounting instead of `chars/4`.
- `finishReason` → real `length` / `stop` / `safety`, which the DOM path can only
  guess.

## Concurrency

`httpx.AsyncClient` with HTTP/2 multiplexing; slots are logical, not tabs. Start
at one in-flight request, add a slot after N consecutive clean turns, drop back
to one on the first 429 / `PERMISSION_DENIED`. The pacing sleep that used to be
hard-coded in `queue_worker` becomes this controller (`STREAM_INTERSTREAM_DELAY_S`
stays as a manual floor).

Attribution is per-task: each request owns its stream and its parser instance, so
`CURRENT_STREAM_REQ_ID` and the global `STREAM_QUEUE` are not needed on this path.

## Fallback ladder

1. `RPC_MODE=rpc`: try the replica. On transport error or 5xx → retry once.
2. On 4xx (auth/build drift) → re-capture the template from the live tab, retry
   once.
3. Still failing → serve this request through the DOM path (today's worker) and
   demote the mode for the rest of the session, with a counter so it is visible
   in `/health`.

Kill criterion, stated as a rate: if the RPC path fails more than 10 % of turns
over a 20-turn window, it is not reliable enough to be default, regardless of how
fast it is.

## Config surface

| name | default | meaning |
| --- | --- | --- |
| `RPC_MODE` | `dom` | `dom` / `rpc` / `auto` (try rpc, fall back) |
| `RPC_TEMPLATE_PATH` | `auth_profiles/rpc_template.req` | captured body used as template |
| `RPC_CAPTURE_LIMIT` | `25` | capture budget per process (`0` disables) |
| `RPC_MAX_INFLIGHT` | `1` | initial concurrency |
| `RPC_REFRESH_AT_BEFORE_S` | `600` | refresh `at` this long before its observed expiry |

## Acceptance checks (deferred — no behavioural testing was run)

Design them before writing code, run them on the Windows host:

1. Same prompt, `RPC_MODE=dom` vs `rpc`: identical text for `temperature=0`,
   `seed` set.
2. Tool turn: model issues a call, result is fed back, model does not re-issue
   the identical call (the defect `FORK-NOTES.md` §2 records for the DOM path).
3. `max_tokens=16` returns `finish_reason=length` and ≤16 output tokens.
4. `usage.prompt_tokens` within a few percent of AI Studio's own display for the
   same chat.
5. Kill criterion: 20 consecutive turns at ≥95 % success before flipping the
   default.

## What would make this the wrong plan

If the captured body turns out to carry a per-request signature that the page's
JS computes (not a reusable `at`), replay dies on the first attempt and the honest
answer is S1 (in-page tee + per-request routing) plus the compat fixes, not RPC.
That is why the capture comes first and the template decision is deferred to real
bytes rather than assumed.
