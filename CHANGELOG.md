# Changelog

All notable changes to `aipf` are documented in this file.

The project follows semantic versioning after the first public release:

- Patch releases fix bugs, packaging issues, or documentation.
- Minor releases add checks, CLI options, or backward-compatible report/capture fields.
- Major releases may break `RunReport`, capture schema, CLI defaults, or provider contracts.

## [0.1.0] - 2026-05-27

Initial public release candidate.

### Added

- Async CLI audit flow for OpenAI- and Anthropic-compatible LLM proxy APIs.
- Model discovery, completion, streaming, prompt-injection, wrapper-leak,
  provider-fingerprint, tool-ID, and latency checks.
- Strict Pydantic JSON report contract with deterministic exit codes.
- Redacted debug trace mode for request lifecycle, provider selection, retries,
  streaming chunk events, model resolution, and timing.
- Sanitized capture/replay subsystem with schema versioning and bounded file sizes.
- Modern Rich-based CLI rendering with compact status output.
- Project documentation for architecture, risk zones, capture/replay, positioning,
  branding, use cases, and contribution workflow.

### Security

- API keys, bearer tokens, authorization headers, and known secret patterns are
  redacted from diagnostic output.
- Capture files store sanitized metadata only and do not store raw request bodies,
  request headers, API keys, or raw response bodies.
- Replay mode never makes outbound HTTP requests.

### Packaging

- Hatchling-based build backend.
- `aipf` console script entrypoint.
- MIT license metadata and license file.
- Source distribution includes docs, tests, architecture notes, and branding assets.
