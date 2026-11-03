# Fork notes â€” revived + hardened

Upstream HEAD at clone: `044c3db` (2026-04-22). This checkout is the same code
with the dependency drift fixed and the behavioural fingerprint reworked.

## 1. Why it did not run

Upstream pins predate wheels for current interpreters:

| pin | problem |
| --- | --- |
| `cryptography==42.0.5` | no cp313/cp314 wheel, needs Rust |
| `aiohttp~=3.9.5` | C extension, no current wheel |
| `pillow^10.0.0` | no cp313+ wheel |
| `requests==2.31.0`, `fastapi==0.115.12`, `uvicorn==0.29.0` | held back roughly a year |

There is no Poetry on this machine and Python 3.15 is the system interpreter, so
the project was bootstrapped on a **standalone CPython 3.12** (via `uv`, no
admin) with relaxed floors. `requirements.txt` records the exact working set.

Result: `tools/import_sweep.py` imports **115/115** project modules clean, and
`server.py` starts and serves `/health` and `/v1/models`.

## 2. What was changed for detection resistance

The proxy drives a real browser, so the thing being fingerprinted is the
*browser session*, not the HTTP client. Fixes are ordered by how cheap the tell
was to detect.

### 2.1 Prompt entry (`browser_utils/human_input.py`, new)

Was:

```js
element.value = text;
element.dispatchEvent(new Event('input',  {bubbles: true}));
element.dispatchEvent(new Event('change', {bubbles: true}));
```

One event, no keystrokes, no caret movement, whole string inside a single
event-loop turn. Now, verified by `tools/verify_stealth.py` against a real
build with an instrumented textarea:

| prompt | events |
| --- | --- |
| 31 chars | 39 `keydown`, 39 `keyup`, 32 `beforeinput`, 31 `input` |
| 2540 chars | 2 `beforeinput` (`inputType: insertText`), 1 `input` |

Short prompts get real key events (humanized by Camoufox). Long ones use the
paste/IME primitive, which is exactly what a human pasting a long prompt
produces â€” 2540 keystrokes would be the *unrealistic* shape. Every path is
verified by reading the field back; the legacy assignment survives only as a
last-resort fallback.

Callers patched: `page_controller.submit_prompt` (live path) and
`page_controller_modules/input.py` (kept consistent).

### 2.2 Launch-time coherence (`launch_camoufox.py`)

`build_stealth_launch_config()` adds:

- **humanize** â€” bezier cursor paths + keystroke cadence. Without it every
  click teleports to element centres.
- **geoip** â€” timezone, geolocation and WebRTC candidates derived from the
  egress IP, with a **bounded pre-flight** (`_bounded_call`, 15 s budget). The
  upstream-style call would otherwise stall the launch for minutes when the
  IP-echo service is slow.
- **timezone pin** â€” a generated preset can carry its own timezone, and
  Camoufox will not overwrite a value the caller set. Unpinned, a session could
  report `Asia/Kolkata` while egressing from Frankfurt. Pinned to the geoip
  result, or the host zone when geoip is unavailable.
- **locale en-US** â€” deliberate. Every selector in `config/selectors.py` is an
  English aria-label; letting geoip choose the UI language translates them away.
- **fingerprint_preset** â€” coherent identity instead of independently
  randomised values.
- **screen bound** â€” `Screen(min_width=1536, min_height=864)`.
- **firefox_user_prefs** â€” `dom.webdriver.enabled=false`,
  `media.peerconnection.ice.no_host`, `...default_address_only`, and
  `...proxy_only_if_behind_proxy` when a proxy is configured.

### 2.3 Geometry (`browser_utils/initialization/core.py`)

Two impossible-geometry bugs removed:

- viewport `460x800` inside a `1440x900` window â€” a 980 px `innerWidth` vs
  `outerWidth` gap cannot occur on a real desktop. Now `no_viewport=True`
  (actual window size); `CAMOUFOX_VIEWPORT=WxH` restores a fixed pane.
- a forced `window=(1440, 900)` against a generated `1280x672` screen produced
  `outerHeight 805 > screen.height 672`. Measured, not assumed:

  ```
  preset + screen bound, no window   screen 1600x852  outer 1280x805   ok
  preset + window 1440x900           screen 1280x672  outer 1280x805   impossible
  ```

  The forced window is gone; Camoufox sizes the window to the screen it picked.

- `ignore_https_errors` is now `False` (`ALLOW_INSECURE_TLS=true` only behind a
  TLS-inspecting proxy). Accepting bad certs is itself observable.

### 2.4 Not changed

- Parameter panel edits (`temperature`, `top_p`, â€¦) still use direct value
  assignment. They happen inside the run-settings dialog, are one-shot, and are
  not part of the prompt-submission path. Lower value, higher regression risk.
- Request pacing is unchanged: the queue serialises to one browser context, so
  traffic is already naturally spaced.

## 3. Running it

```powershell
.\run.ps1 -Mode setup      # one-time: 3.12 venv, deps, browser, geoip, verify
.\run.ps1 -Mode debug      # first run: log into Google in the window, then Enter
.\run.ps1 -Mode headless   # daily use once auth_profiles/active/ is populated
.\run.ps1 -Mode verify     # re-run the anti-detection checks
.\run.ps1 -Mode api        # FastAPI only, no browser (config smoke test)
```

`AUTO_SAVE_AUTH=true` is set, so the debug-mode login writes a profile
automatically. Headless mode then needs `ACTIVE_AUTH_JSON_PATH` or
`AUTO_AUTH_ROTATION_ON_STARTUP=true`.

Then point a client at `http://127.0.0.1:2048/v1`.

## 4. Verified state

| check | result |
| --- | --- |
| `tools/import_sweep.py` | 115/115 modules import |
| `server.py` `/health` | 200, queue running |
| `launch_camoufox.py --debug` | Camoufox boots, WS captured, navigates to AI Studio, stops at the login wall as designed |
| `[stealth] geoip bound` | `203.0.113.10 -> Asia/Kolkata` in 0.6 s after the MMDB was pre-seeded |
| `tools/verify_stealth.py` | `navigator.webdriver=false`, `innerWidth==outerWidth`, window fits screen, keystroke shapes as above |

**Not verified:** an authenticated turn. That needs a Google session, which is
the one step that cannot be automated here.

## 5. Latency: where the 52 s went (and what it costs now)

First working request measured 52.4 s. Instrumented breakdown:

| stage | before | now |
| --- | --- | --- |
| temperature/top_p/stop fills (5 s timeout each, panel collapsed) | ~15 s | 2.4 s (probed once, skipped) |
| model switch | 11.9 s | 0 s when cached |
| submit (type + await Run-enabled + click) | 10.3 s | 10â€“13 s |
| generation (thinking level High) | ~10 s | ~3.8 s (`low`) |
| chat-history clear (blocks the next request) | ~5 s | ~5 s |
| **wall clock** | **52.4 s** | **~26 s** |

Fixes: `_ensure_advanced_settings_expanded()` gate (the panel is collapsed, so
the controls were absent from the DOM and every fill burned its full timeout);
`DEFAULT_THINKING_LEVEL_FLASH=low`; faster Run-enabled polling.

### The floor

~25 s is structural for this design, not a bug:

- one browser context serialises every request (queue + lock),
- each request is prefixed by a chat-history clear so conversations don't bleed,
- the prompt must be typed and the Run control awaited through the DOM,
- Camoufox humanize costs ~157 ms/char while typing and ~1.2 s per humanised
  click, which is the price of the keystroke realism added in section 2.

Knobs: `HUMAN_TYPE_MAX_CHARS=0` (always paste â€” saves ~3â€“5 s on short prompts,
loses per-key events), `DEFAULT_THINKING_LEVEL_FLASH` / `reasoning_effort`.

### If you need real API latency

Driving the UI is the wrong transport for that. The fast path is to skip the
page entirely and speak AI Studio's internal `batchexecute` / `MakerSuiteService`
RPC directly with the same cookies â€” sub-second to a few seconds, but a
completely different (and much more brittle) detection surface. The UI proxy
buys resilience by being indistinguishable from a user, and pays for it here.

## 6. Gotchas for the next session

- `camoufox fetch` (1.2 GB) and the GeoIP MMDB (50 MB) both stream from the
  GitHub release CDN with no resume and stall on throttled links. Use
  `tools/install_camoufox_zip.py` / `tools/install_geoip_zip.py` with a
  curl-downloaded archive instead.
- Playwright's Firefox evaluates in a sandbox that shares the DOM but **not**
  JS globals: `page.evaluate("window.foo")` sees `undefined` even when page
  script set it. Log through the DOM instead.
- `python-dotenv` is loaded before other imports in `launch_camoufox.py`;
  keep `.env` values authoritative, CLI flags override.
- `customtkinter` resolved to 6.0.0 (upstream expected ^5.2). The desktop GUI
  launcher is optional and has not been exercised.
- `skills`/frontend: `static/frontend/dist` is generated output and is
  gitignored upstream. It was built here with `npm.cmd ci && npm.cmd run build`
  (Node 24). `npm` via PowerShell `.ps1` is blocked by execution policy on this
  machine â€” use `npm.cmd`.

## 7. Conversation sessions (agent mode)

Upstream cleared the chat after every request and re-serialised the whole
`messages` array into one prompt. For an agent that is O(n^2): turn N re-uploads
turns 1..N-1 as fresh text. `api_utils/chat_sessions.py` keeps the chat loaded
and submits only the new tail.

Bookkeeping per session: `client_fps` (fingerprints of everything the client has
sent), `page_len` (how many of those the page holds, plus one for the assistant
reply the client has not sent back yet), `base_index` / `handoff` (rotation
state), `page_tokens`.

Rules:

- key = hash(system prompt + first user message + model + tools signature);
- a delta is used only when the stored fingerprints are a strict PREFIX of the
  incoming history - rewritten or truncated history replays into a cleared
  chat, and can never silently inherit a diverged conversation;
- an empty delta (client resent history without a new turn) replays instead of
  submitting an empty prompt;
- SESSION_REUSE_ENABLED=false restores upstream behaviour.

`page_len` counts the assistant reply as +1 on purpose. Without it the next
delta starts at the reply the client now includes, and the model's own answer
gets re-submitted as a fresh assistant turn.

### Rotation at the context ceiling

At SESSION_CONTEXT_LIMIT_TOKENS (default 900k, SESSION_CHARS_PER_TOKEN=3.5) the
worker runs one summarisation turn IN THE SAME CHAT (api_utils/session_rotation.py),
stores the reply as the handoff, clears, and seeds the next chat with
HANDOFF_PREFIX + summary + HANDOFF_SUFFIX on the first turn only. Because the
previous handoff is part of what the model summarises, summaries chain.

A failed summary invalidates the session rather than guessing; the next request
does a full replay.

## 8. Model policy: pin to the newest Flash

AI_STUDIO_FORCE_MODEL=gemini-3.8-flash makes the client's `model` field
advisory: analyze_model_requirements logs the substitution and switches the page
regardless of what was requested ("gpt-4o" works). Empty/off/auto restores
per-request selection.

AI_STUDIO_MODEL_FALLBACKS is the ordered chain; its first entry is also what the
init recovery writes into localStorage.aiStudioUserPreference.promptModel when
the persisted model is gated and the composer never renders.

Measured with a clean browser, one tiny prompt each:

| model | result |
| --- | --- |
| gemini-3.8-flash | OK |
| gemini-3.5-flash-lite | OK |
| gemini-3.1-flash-lite | OK |
| gemini-3.1-pro-preview | OK |
| gemini-3.6-flash | hung (no turn, no error) |
| gemini-3-flash-preview | gated (upsell wall) |

## 9. The 403 that is not an entitlement problem

AI Studio reports free-tier throttling as gRPC PERMISSION_DENIED, surfaced as
"403 Forbidden" from GenerateContent. It is indistinguishable from a real
permission error except that it clears by itself in minutes, and the page shows
"Permission denied. Please check your account permissions and project settings."

Observed pattern: 2-3 generations of the same model in quick succession, then
403 for that model for a few minutes, while a different model still works. That
is a per-model request bucket, not a daily token wall.

The proxy maps a 403 to 429 + Retry-After: 30 (error_utils.throttled) so
OpenAI-compatible agents back off instead of treating the turn as fatal.

## 10. Dialogs and backdrops that wedge the page

Two distinct blockers, both fatal and both invisible in a screenshot:

1. A confirmation dialog with no close affordance ("New chat" while the
   composer has text: "Content of your current prompt will be deleted" /
   "Discard and continue"). It owns focus, so every later click times out.
2. A leaked transparent backdrop: the dialog closed but
   `.cdk-overlay-backdrop-showing` stayed mounted, intercepting all pointer
   events. Run never enables.

browser_utils/overlays.py::dismiss_blocking_dialogs now handles both: it clicks
close buttons, then an explicit "Discard and continue", then removes backdrops
that have no mat-dialog-container pane behind them.

## 11. Timing instrumentation

`[Timing] params_probe/params_total` (page_controller) and
`[Timing] submit visible/overlays/fill/runable/prep/pause/click`
(page_controller.submit_prompt). Read these before optimising anything:

- a failing advanced-settings probe used to cost ~10s per request; the negative
  result is now cached per page for 180s, so it becomes one DOM query;
- humanize as a float (CAMOUFOX_HUMANIZE_MAX_TIME=0.55) caps cursor travel.
  Unbounded humanize measured 3.5-5s per click - slow, and less human than a
  normal hand movement;
- typing uses real key events only up to HUMAN_TYPE_MAX_CHARS (40). At
  ~157ms/char, anything longer goes through insert_text.

