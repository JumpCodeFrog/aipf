# OSS Positioning

## One-line Description

`aipf` is a forensic CLI for OpenAI/Anthropic-compatible LLM proxy APIs.

## Short Description

`aipf` audits LLM proxy behavior across model discovery, completions, streaming,
provider-style detection, retry behavior, prompt/wrapper leaks, latency, and
sanitized capture/replay timelines.

## Elevator Pitch

Point `aipf` at an LLM proxy and get a structured view of how it behaves: which
models it exposes, whether streaming works, how retries look, whether wrapper details
leak, which provider it resembles, and how to replay a debugging timeline offline.

## Hacker News Friendly Intro

LLM proxies often claim OpenAI or Anthropic compatibility, but the details that
break integrations are usually in streaming, retries, provider routing, and wrapper
behavior. `aipf` is a small async CLI that probes those surfaces and writes a redacted
JSON report you can use in CI, migration notes, or incident debugging.

## Problem Statement

Teams increasingly put LLM traffic behind gateways, internal proxy APIs, vendor
routers, and compatibility layers. Those layers simplify integration, but they also
make behavior harder to inspect.

Common failure modes:

- model lists do not match routable models;
- OpenAI-shaped APIs route to Anthropic-style models;
- streaming succeeds while non-streaming fails, or the reverse;
- retries hide provider or gateway instability;
- wrapper prompts, system instructions, or tool IDs leak into responses;
- failures are hard to reproduce after the original run.

`aipf` exists to make those behaviors visible with a repeatable CLI workflow.

## Positioning Pillars

### Forensic, Not Evaluative

`aipf` does not grade model quality. It inspects API behavior, provider compatibility,
streaming shape, retry paths, leaks, and timing.

### CLI-First

The primary interface is a fast terminal tool that works locally, in CI, and in
incident workflows. There is no server process, database, daemon, or web UI.

### Safe Diagnostics

Diagnostics are useful only if they do not create a second security incident. `aipf`
redacts known secret shapes and avoids raw request/response payload storage in debug
and capture modes.

### Structured Contracts

Reports are strict Pydantic models. Capture files are schema-versioned. Debug and
capture are separate from the report contract.

### Provider-Aware Compatibility

`aipf` knows the operational differences between OpenAI-style and Anthropic-style
APIs and keeps provider detection explicit.

## Tone Guide

Use:

- "forensic CLI"
- "LLM proxy audit"
- "provider-compatible API"
- "redacted JSON reports"
- "sanitized capture/replay"
- "repeatable debugging"

Avoid:

- "magic firewall"
- "unbreakable security"
- "military-grade"
- "10x observability"
- "magic detection"
- broad claims about model safety or jailbreak prevention.

## Comparison Language

`aipf` should be compared by scope, not by superiority:

- Compared with `curl`, it gives repeatable LLM-specific probes.
- Compared with mitmproxy, it focuses on target API behavior rather than traffic
  interception.
- Compared with eval frameworks, it checks protocol and proxy behavior rather than
  task quality.
- Compared with gateway metrics, it is an on-demand forensic tool rather than a
  production telemetry backend.

## Roadmap v1

Suggested v1 scope:

1. Stabilize report schema and capture schema v1.
2. Add more provider-detection fixtures for mixed and non-standard `/v1/models`.
3. Expand streaming parser fixtures: comments, keepalive, multiline data, non-JSON chunks.
4. Add explicit report schema documentation.
5. Add CI release workflow: test, lint, typecheck, build wheel/sdist.
6. Publish to PyPI with signed release artifacts if practical.
7. Add versioned changelog and upgrade notes.
8. Decide the fate of existing impersonation models: remove or implement as a check.

## Future Ecosystem Integrations

Useful integrations that fit the project boundary:

- GitHub Actions examples for proxy smoke checks.
- Pre-deploy CI jobs for staging proxy compatibility.
- JSON report upload hooks for existing security data lakes.
- SARIF-like export for security scanners, if findings semantics mature.
- OpenTelemetry span export from capture/debug events, behind an opt-in adapter.
- Markdown report summaries for PR comments.
- Dataset fixtures for known proxy compatibility patterns.

Avoid integrations that turn `aipf` into a server, persistent monitor, hosted service,
or generic SDK.

## Possible Plugin System

A plugin system could be useful after the core check contract is stable.

Minimal direction:

- entrypoint-based discovery, for example `aipf.checks`;
- strict plugin metadata: name, version, result kind, supported provider styles;
- plugin checks receive `AsyncProxyClient` and `RunContext`;
- plugin results must be strict Pydantic models;
- plugin network traffic must still go through `AsyncProxyClient`;
- plugin tests should use `respx`.

Risks:

- report schema fragmentation;
- unsafe logging by third-party checks;
- prompt battery false positives;
- dependency bloat.

Recommendation: postpone plugins until v1 report/capture compatibility is documented.

## PyPI Release Strategy

Recommended path:

1. Keep package name `aipf` if available; otherwise choose a clear alternate like
   `ai-proxy-forensics`.
2. Add `CHANGELOG.md` before first public release.
3. Add release CI that runs `pytest`, `ruff check src tests`, `mypy`, and wheel/sdist build.
4. Publish from tags only.
5. Use semantic versioning:
   - patch: bugfixes and docs;
   - minor: new checks or non-breaking report/capture fields;
   - major: breaking report or capture schema changes.
6. Document supported Python versions and provider compatibility.
7. Treat `RunReport` and `CaptureFile` as public contracts.

## GitHub Presentation Checklist

- README explains the problem in the first screen.
- Quickstart works from a fresh clone.
- Security guarantees are explicit.
- Examples show real CLI output, not screenshots only.
- Roadmap is practical and scoped.
- No claims that imply full model security coverage.
- Issues are labeled by area: `client`, `checks`, `reports`, `capture`, `docs`,
  `security`, `provider-compat`.
