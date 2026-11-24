# Contributing

Thanks for helping improve AI Studio Proxy API. This repository is a hardened
fork of [CJackHwang/AIstudioProxyAPI](https://github.com/CJackHwang/AIstudioProxyAPI),
tuned to work as an agent backend; the upstream project is the foundation.

Two kinds of change are welcome:

- **correctness and compatibility on this transport** — wrong output, lost text,
  a field accepted but not honoured, a failure reported as success. These are the
  most valuable contributions.
- **performance work**, if it comes with evidence. Latency claims without a
  measurement tend to be guesses about a browser nobody can benchmark in a unit
  test.

## Before you start

Read these two files, in this order:

- [`FORK-NOTES.md`](FORK-NOTES.md) — changes that were **measured**, with the
  before/after numbers behind them.
- [`OPTIMIZATION.md`](OPTIMIZATION.md) — analysis that is **reasoned but not yet
  measured** on this hardware, kept separate on purpose.

The split matters. A change backed by a measurement belongs in the first file; a
change backed by reading the code and a static check belongs in the second. If
you cannot say which one your change is, it is probably not ready.

## Local development

```bash
git clone https://github.com/Kaiso-666/aistudio-proxy-api.git
cd aistudio-proxy-api
poetry install --with dev
cp .env.example .env
```

The README also documents a plain `pip install -r requirements.txt` path; use
whichever your environment supports. A browser is only needed to run the proxy
against AI Studio, not to run most of the test suite.

## Checks before you push (required)

```bash
poetry run ruff check .
poetry run pyright
poetry run pytest
```

If you touched the streaming wire path (`stream/`), also run the dependency-free
decoder regression — it needs nothing but a Python 3 interpreter:

```bash
python3 tools/check_stream_decoder.py
```

It replays gzip/chunked response bodies in **cumulative one-byte reads**, the way
`stream/proxy_server.py` feeds them, and asserts exact text for plain, compressed,
chunk-extension, trailer-terminated and split-multi-byte cases. A decoder change
that breaks a frame boundary shows up here in seconds instead of as "the answer
was cut" in a client.

If you touched the frontend:

```bash
cd static/frontend
npm ci
npm run build
npm run test
```

There is no CI pipeline in this fork. The checks above are the gate; run them
before opening a pull request, and say in the description what you ran.

## Testing philosophy

- Prefer a check that can actually run here. If a behaviour needs the browser,
  say so and state exactly which command would prove it — do not assert it works.
- Pure functions (parsing, validation, fingerprints, token estimates) should be
  exercised directly, including the malformed input they are meant to survive.
- When you change behaviour that a test asserted, change the test **and its
  docstring**: a test that encodes a bug is worse than no test, because the next
  reader treats it as a specification.

## Branch and commit conventions

- `feat/...` new capability
- `fix/...` defect
- `docs/...` documentation only
- `refactor/...` no behaviour change

Commit messages follow Conventional Commits:

- `feat:` new capability
- `fix:` defect
- `docs:` documentation
- `refactor:` restructuring
- `test:` test-only change
- `chore:` tooling or housekeeping

Explain *why* in the body, not just what. One defect per commit when possible;
the "why" is what a future reader cannot recover from the diff.

## Pull requests

- State the motivation, the approach, and the blast radius (which paths a request
  can reach that could not before).
- Config or interface change → update `README.md` and, where relevant, `docs/`.
- New environment variable → add it to `.env.example` with its default and what
  it changes. Four documented knobs had been missing from that file; treat the
  check as a review item, not a formality.
- Keep the diff minimal. No drive-by reformatting: it hides the actual change and
  makes review harder than the bug.

## Documentation map

- `README.md` — what the proxy is, how to run it, what it deliberately refuses.
- `FORK-NOTES.md` / `OPTIMIZATION.md` — why the fork exists (measured / reasoned).
- `docs/architecture/RPC-MODE.md` — the plan for replacing the browser transport
  with a direct `batchexecute` replay, and its kill criteria.
- `docs/*.md` — upstream documentation, still accurate for shared settings. These
  are in Chinese; the fork's own notes are in English.

## Reporting an issue

Include as much of this as you can:

- steps to reproduce, and whether streaming or non-streaming;
- expected behaviour vs. actual behaviour;
- Python version and operating system;
- whether `AI_STUDIO_FORCE_MODEL` is set;
- relevant logs (`logs/`, `errors_py/`), and `/health` output. If timings are part
  of the problem, set `TURN_TIMING=1` first — the phase split says more than a
  wall-clock total.

Redact cookies, tokens and prompts before pasting anything.

## Upstream

Fork-specific behaviour (model pinning, truncation reporting, response-format
handling, the refusal list) is not something upstream has to accept. If a fix is
generic — a decoder bug, a timeout that ignores live generation — say so in the
pull request; it is worth sending upstream as well.
