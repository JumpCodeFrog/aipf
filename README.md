# aipf — API Proxy Forensics Toolkit

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-green)](https://docs.pytest.org/)
[![Style](https://img.shields.io/badge/style-ruff-black)](https://docs.astral.sh/ruff/)
[![Typing](https://img.shields.io/badge/typing-mypy-blue)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](#license)

[Русская версия](README.ru.md)

`aipf` is an async CLI for auditing OpenAI- and Anthropic-compatible LLM proxy APIs.
It helps teams understand what a proxy exposes, how it behaves under streaming and
retry conditions, whether wrappers leak implementation details, and how to reproduce
debug sessions without making the same network calls again.

It is deliberately small: no server, no database, no browser UI, no background
worker. Just a developer-first forensic CLI with structured JSON reports, redacted
logs, debug traces, and sanitized capture/replay.

## Why aipf exists

LLM proxy APIs are now common in internal platforms, hosted gateways, automation stacks,
and vendor abstraction layers. They often claim OpenAI or Anthropic compatibility,
but the practical behavior can differ in ways that matter:

- `/v1/models` may not reflect what the proxy can actually serve.
- A proxy may expose an OpenAI-shaped API while routing to Anthropic-style models.
- Streaming may work differently from non-streaming completions.
- Retry and timeout behavior can hide proxy-side degradation.
- Wrapper prompts and provider-specific tool IDs can leak through responses.
- Debugging is hard when failures depend on timing and provider selection.

`aipf` gives you a repeatable probe battery and a report format you can use in CI,
incident notes, proxy migrations, and vendor compatibility checks.

## When to use aipf

Use `aipf` when you need to:

- validate an OpenAI/Anthropic-compatible proxy before integrating it;
- compare staging and production proxy behavior;
- debug provider-style auto-detection issues;
- check that streaming and non-streaming endpoints behave consistently;
- capture a failing session and replay its timeline offline;
- audit wrapper leaks, tool-call identifiers, and provider fingerprints;
- produce a structured JSON report for automation.

Do not use `aipf` as a proxy server, SDK, load tester, policy engine, or model eval
framework. It is a focused CLI for API forensics.

## Quickstart

Requires Python 3.11+.

From a source checkout, install the CLI:

```bash
git clone <repo-url>
cd aipf
pipx install -e .
```

After the first PyPI release:

```bash
pipx install aipf
```

Start the guided menu:

```bash
aipf
```

In a normal terminal this opens the main menu. In non-interactive environments
without stdin TTY, `aipf` prints help and exits.

Menu navigation is intentionally simple:

- `Enter` selects the default action where one is shown;
- `b` or `back` returns to the previous menu;
- `0` returns from submenus or exits from the main menu;
- `q`, `quit`, or `exit` exits the CLI.

Configure the target proxy:

```env
AIPF_BASE_URL=https://your-proxy.example.com
AIPF_API_KEY=sk-...
AIPF_MODEL=claude-haiku-4-5-20251001
AIPF_API_STYLE=auto
```

Or create a local `.env` from the template:

```bash
cp .env.example .env
```

Run the full probe battery:

```bash
aipf run --output report.json
```

Or pass options directly:

```bash
aipf run \
  --base-url https://your-proxy.example.com \
  --api-key "$AIPF_API_KEY" \
  --model gpt-test \
  --api-style auto \
  --output report.json
```

If you do not know the model ID yet, start with model discovery:

```bash
aipf models \
  --base-url https://your-proxy.example.com \
  --api-key "$AIPF_API_KEY"
```

Recommended first-run flow:

1. `aipf models` to verify auth, base URL, and visible model IDs.
2. `aipf completion --model <id>` to verify non-streaming behavior.
3. `aipf stream --model <id>` to verify SSE streaming behavior.
4. `aipf run --model <id>` for the full audit.

## CLI examples

### Full audit

```text
aipf | async LLM proxy audit | mode=run | provider=openai | model=gpt-test | endpoint=https://mock.example.com
running 8 checks | provider=openai
01/08 RUN MODELS
01/08 [PASS] MODELS 1ms 2 model(s)
02/08 RUN COMPLETION
02/08 [PASS] COMPLETION 1ms 3 token est.
03/08 RUN STREAM
03/08 [PASS] STREAM 1ms 3 chunks
...
report=report.json
summary | model=gpt-test | provider=openai | passed=8 | warning=0 | failed=0 | error=0 | skipped=0
```

### Single checks

```bash
aipf models
aipf completion --model gpt-test
aipf stream --model gpt-test
aipf inject --model gpt-test
aipf leaks --model gpt-test
aipf fingerprint --model gpt-test
aipf tool-ids --model gpt-test
aipf latency --model gpt-test --latency-rounds 10
```

Single-check commands print the result JSON and can also write a mini report:

```bash
aipf completion --model gpt-test --output completion-report.json
```

### Interactive mode

```bash
aipf interactive
```

Interactive mode prompts for endpoint URL and API key, detects provider style,
fetches `/v1/models`, lets you pick a model, and runs the full battery.

Desktop-friendly launchers are included:

- Windows: `run-aipf-interactive.bat`
- Linux: `run-aipf-interactive.sh`

## Debug mode

Debug mode prints redacted lifecycle events to stderr. It is separate from the JSON
report and does not include request headers, request payloads, or raw response bodies.
Use it when a run fails because of provider selection, retry behavior, endpoint shape,
streaming state, or model resolution.

```bash
aipf completion --model gpt-test --debug
aipf completion --model gpt-test --debug-format json --debug
```

Example:

```text
trace +0.19ms model.resolve check=completion source=settings model=gpt-test
trace +5.37ms client.init base_url=https://mock.example.com declared_style=openai timeout_s=90
trace +5.54ms chat.request.build style=openai endpoint=/v1/chat/completions model=gpt-test max_tokens=512 stream=false
trace +5.63ms http.request.start trace_id=req-d728b0312da method=POST url=https://mock.example.com/v1/chat/completions attempt=1 stream=false
trace +6.36ms http.request.end trace_id=req-d728b0312da status=429 latency_ms=0.69 attempt=1 stream=false
trace +6.42ms http.retry trace_id=req-d728b0312da next_attempt=2 sleep_s=0.0 reason=retry-after status=429
```

## Capture and replay

Capture saves a sanitized forensic timeline. Replay renders that timeline without
making HTTP requests.

```bash
aipf completion --model gpt-test --capture capture.json
aipf replay capture.json
aipf replay capture.json --format json
```

To keep all generated artifacts together:

```bash
aipf run --model gpt-test --artifacts-dir audit-2026-05-27
```

Replay example:

```text
capture schema=v1 command=completion events=11 truncated=false
0001 trace +0.25ms model.resolve check=completion model=gpt-test source=settings
0006 trace +5.93ms http.request.start attempt=1 method=POST path=/v1/chat/completions
0007 trace +6.64ms http.request.end attempt=1 status=429 latency_ms=0.66
0008 trace +6.74ms http.retry next_attempt=2 reason=retry-after sleep_s=0.0 status=429
```

Capture files are versioned, deterministic JSON. They store sanitized metadata only:
no raw prompts, request bodies, request headers, API keys, or raw response bodies.
They are useful for bug reports and provider analysis, but they are still operational
artifacts: endpoint paths, model names, timing, retry behavior, and status codes may
be sensitive.

See [docs/capture-replay.md](docs/capture-replay.md) for the schema and compatibility
rules.

See [SECURITY.md](SECURITY.md) for responsible disclosure, security boundaries,
redaction limitations, and artifact handling guidance.

## Feature matrix

| Area | What aipf checks | Output |
| --- | --- | --- |
| Models | `/v1/models` reachability and model IDs | `models_list` result |
| Completion | Non-streaming chat/message response extraction | `completion` result |
| Streaming | SSE shape, chunk count, first chunk timing | `streaming` result |
| Prompt injection | Small prompt-injection battery | `injection` result |
| Wrapper leaks | Known leak phrases and snippets | `leaks` result |
| Provider fingerprint | OpenAI/Anthropic-style response patterns | `fingerprint` result |
| Tool IDs | `toolu_`, `call_` style identifiers | `tool_ids` result |
| Latency | Sequential request timing stats | `latency` result |
| Debug trace | Request lifecycle, retries, provider selection | human or JSON trace |
| Capture/replay | Sanitized timeline for offline debugging | schema-versioned capture |

## Provider support

| Provider style | Endpoint | Auth shape | Status |
| --- | --- | --- | --- |
| OpenAI-compatible | `/v1/chat/completions` | `Authorization: Bearer ...` | supported |
| Anthropic-compatible | `/v1/messages` | `x-api-key`, `anthropic-version` | supported |
| Auto-detect | `/v1/models` probe | combined probe headers | supported |

Auto-detection is conservative: if model IDs look Anthropic-only, `aipf` uses the
Anthropic adapter; otherwise it falls back to OpenAI-style requests. You can override
this with `--api-style openai` or `--api-style anthropic`.

## Reports and exit codes

`aipf run` writes:

- a JSON report, default `aipf-artifacts/reports/report-<timestamp>.json`;
- structured JSON logs, default `aipf-artifacts/logs/forensics.log`;
- optional debug trace via `--debug`;
- optional sanitized capture file via `--capture`.

`--artifacts-dir PATH` changes default artifact locations to:

```text
PATH/
  reports/
  logs/
  captures/
```

Explicit paths still win: `--output`, `--log-file`, and `--capture` write exactly
where you point them.

Exit codes:

- `0` — no warnings or errors;
- `1` — at least one check errored;
- `2` — warnings without errors.

The JSON report is a strict Pydantic contract and is separate from debug traces and
capture files.

Artifact contracts:

| Artifact | Default | Format | Contract |
| --- | --- | --- | --- |
| Report | `aipf-artifacts/reports/report-<timestamp>.json` | strict JSON | Public `RunReport` schema |
| Log | `aipf-artifacts/logs/forensics.log` | JSON lines | Diagnostic runtime log |
| Debug trace | stderr only | human or JSON | Opt-in lifecycle events |
| Capture | opt-in path, or `PATH/captures/capture.json` with `--artifacts-dir` | deterministic JSON | Versioned `CaptureFile` schema |

Compatibility expectations:

- New checks may add new result `kind` values in future minor releases.
- Existing `RunReport` fields should remain backward-compatible within `0.x` unless
  release notes call out a schema change.
- Capture files are versioned separately from reports via `schema_version`.
- Consumers should ignore unknown optional fields and validate the schema version.

## Security boundaries

`aipf` is designed for proxy forensics, so diagnostic output is intentionally bounded:

- Known API key fields, bearer tokens, `Authorization`, and `x-api-key` values are
  passed through redaction.
- Request headers and request bodies are not logged by default.
- Raw response bodies are not logged at INFO level.
- Capture files store sanitized metadata only.
- Replay never makes network requests.
- Tests use `respx`; no test should call a real proxy.

Reports may contain response snippets from the target proxy. Treat reports as
sensitive operational artifacts if the proxy can return confidential data.
Redaction is a defensive layer, not a DLP guarantee.

## Architecture overview

```text
CLI command
  -> Settings
  -> optional debug tracer
  -> optional capture tracer
  -> AsyncProxyClient
  -> provider style detection
  -> check registry / check order
  -> strict Pydantic results
  -> RunReport JSON + exit code

capture JSON file
  -> CaptureFile validation
  -> human or JSON-lines replay
```

The HTTP boundary is intentionally narrow: `src/aipf/client.py` is the only outbound
HTTP adapter. Checks operate through that client and return strict result models.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/backend-map.md](docs/backend-map.md)
for module-level details.

Runtime scope:

- no server process or daemon;
- no database or persistent state beyond files explicitly written by the CLI;
- no real network calls in tests;
- replay mode validates and renders capture files without constructing an HTTP client;
- configuration comes from CLI flags, environment variables, or `.env`.

## Comparison

| Tool category | Useful for | Where aipf fits |
| --- | --- | --- |
| `curl` / HTTPie | Manual endpoint checks | `aipf` runs a repeatable LLM proxy probe battery |
| mitmproxy | Inspecting traffic through a proxy | `aipf` probes provider behavior and emits structured reports |
| LLM eval frameworks | Quality and task evaluation | `aipf` focuses on API behavior, leaks, streaming, retries |
| Gateway observability | Production metrics and traces | `aipf` is an on-demand forensic CLI |
| Custom smoke tests | Team-specific checks | `aipf` provides a maintained baseline for common proxy risks |

## Development workflow

Run tools from the pipx environment:

```bash
pipx inject aipf pytest pytest-asyncio respx ruff mypy
PIPX_AIPF_BIN=$(pipx environment --value PIPX_LOCAL_VENVS)/aipf/bin
"$PIPX_AIPF_BIN/pytest"
"$PIPX_AIPF_BIN/ruff" check src tests
"$PIPX_AIPF_BIN/mypy"
```

Project rules:

- keep `httpx.AsyncClient` as the async HTTP client;
- keep `src/aipf/client.py` as the only outbound HTTP adapter;
- add new checks under `src/aipf/checks/` and register them explicitly;
- keep `RunReport` backward-compatible unless a schema change is intentional;
- test outbound HTTP with `respx`;
- do not add web frameworks, databases, Docker, or frontends without a product need.

## OSS positioning

Concise description:

> `aipf` is a forensic CLI for OpenAI/Anthropic-compatible LLM proxy APIs.

Elevator pitch:

> Point `aipf` at an LLM proxy and get a structured view of models, completions,
> streaming, retries, leaks, provider fingerprints, latency, and reproducible
> capture/replay timelines.

See [docs/positioning.md](docs/positioning.md) and [docs/use-cases.md](docs/use-cases.md)
for use cases, roadmap, release strategy, and future integration ideas.

## License

MIT. See [LICENSE](LICENSE).

Created and maintained by JumpCodeFrog.
