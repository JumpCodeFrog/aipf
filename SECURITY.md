# Security Policy

`aipf` is a forensic CLI for auditing OpenAI/Anthropic-compatible LLM proxy APIs.
This policy describes how to report vulnerabilities and what security boundaries
the project is designed to maintain.

## Supported Versions

Security fixes are provided for the latest public release line.

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |
| `< 0.1.0` | No |

Until `1.0.0`, compatibility-sensitive fixes may still ship in minor releases when
they affect the report schema, capture schema, provider routing behavior, or CLI
contracts.

## Reporting Vulnerabilities

Please report suspected vulnerabilities privately before opening a public issue.

Preferred channels:

- GitHub Security Advisories, if enabled for the public repository.
- A private maintainer contact listed by the repository owner.

If neither channel is available yet, open a minimal public issue that says a private
security report is needed, without including exploit details, secrets, logs, captures,
or vulnerable endpoint URLs.

Include:

- affected `aipf` version and install method;
- operating system and Python version;
- command used, with secrets removed;
- whether `--debug`, `--capture`, or JSON output was enabled;
- minimal reproduction steps using a mock or sanitized target where possible;
- expected impact and any safe proof-of-concept details.

Do not include API keys, authorization headers, raw request bodies, raw prompts, raw
provider responses, private capture files, production endpoint URLs, or customer data.

## Response Policy

The project aims to:

1. Acknowledge valid private reports within a reasonable maintainer window.
2. Triage severity based on exploitability, secret exposure risk, default behavior,
   and impact on report/capture contracts.
3. Fix confirmed issues in the smallest safe change.
4. Add regression tests when the issue affects redaction, logging, report writing,
   capture/replay, provider routing, or CLI exit behavior.
5. Publish release notes that describe impact and upgrade guidance without exposing
   unnecessary exploit details.

Expected severity examples:

- Critical: default behavior exposes API keys, bearer tokens, or authorization
  headers in stdout, stderr, reports, logs, captures, or test output.
- High: replay performs real HTTP requests, capture stores raw request bodies by
  default, or provider routing sends traffic to the wrong API style in a way that
  can expose data.
- Medium: bounded redaction misses a common secret shape in debug/capture output, or
  report metadata leaks more target infrastructure detail than documented.
- Low: hardening, documentation, or edge-case sanitization improvements with limited
  practical exposure.

## Disclosure Expectations

Please allow maintainers time to investigate and prepare a fix before public
disclosure. Coordinated disclosure is preferred when the issue could expose secrets,
production endpoint details, report contents, capture artifacts, or provider routing
behavior.

Public advisories should avoid publishing live credentials, raw customer data, full
proxy payloads, or complete capture files.

## Security Boundaries

`aipf` is designed to preserve these boundaries:

- API keys and authorization material should not be written to normal CLI output,
  JSON logs, debug traces, reports, or capture files.
- Request headers and request bodies are not logged by default.
- Raw response bodies are not logged at INFO level.
- Debug output and capture files use redacted, bounded metadata.
- Capture/replay is separate from the `RunReport` JSON contract.
- Replay reads an existing capture timeline and must not create an HTTP client or
  make network requests.
- Outbound HTTP traffic goes through `src/aipf/client.py`.
- Tests for outbound HTTP use mocks and should not contact real proxies.

## Non-Goals

`aipf` intentionally does not protect against:

- a malicious or compromised target proxy;
- a provider returning sensitive content in normal model responses;
- users saving reports, logs, or captures to insecure locations;
- terminal scrollback, shell history, process listings, filesystem backups, or CI
  artifact retention;
- full data-loss prevention or classification of arbitrary secrets;
- prompt injection prevention for applications using the proxy;
- model safety evaluation, jailbreak prevention, policy enforcement, or content
  moderation;
- secure long-term storage, encryption, key management, or access control for
  generated artifacts;
- network-level interception outside the local `aipf` process.

## Capture / Replay Limitations

Capture files are designed for reproducible debugging, not secure evidence storage.

- Capture stores sanitized metadata only by default, but metadata can still reveal
  target URLs, model names, provider style, timing, status codes, retry behavior, and
  operational structure.
- Streaming events are bounded and sanitized, but they are not a substitute for full
  DLP review.
- Capture files are deterministic JSON and are easy to copy, index, or upload by
  accident.
- Replay does not make HTTP requests, but replay output can still disclose sensitive
  metadata already present in the capture file.
- Truncated captures may omit events needed for full incident reconstruction.

Handle capture files as sensitive operational artifacts.

## Redaction Limitations

Redaction is a defensive layer, not a guarantee.

- Known API key fields, authorization headers, bearer tokens, and configured secret
  values are redacted.
- Unknown secret formats, business identifiers, model output snippets, endpoint
  paths, model names, timing patterns, and provider fingerprints may remain visible.
- Reports may include response snippets from the target proxy. Treat them as
  sensitive if the proxy can return confidential information.
- Debug and capture metadata should be reviewed before sharing outside the trusted
  team.

Do not rely on `aipf` as a DLP system or as proof that an artifact contains no
secrets.

## Proxy Trust Assumptions

`aipf` sends probes to the configured `AIPF_BASE_URL` using the configured API key.
Users are responsible for ensuring that:

- the endpoint is the intended proxy;
- the API key is scoped appropriately for audit probes;
- the proxy is authorized to receive the prompts sent by `aipf`;
- test runs do not target production systems unless that is intentional;
- generated reports and captures are stored according to the sensitivity of the
  target environment.

A malicious proxy can return misleading model lists, malformed streaming data,
adversarial response text, or sensitive content in normal responses. `aipf` can help
surface behavior, but it cannot make an untrusted proxy safe.

## User Recommendations

- Use a dedicated, low-privilege API key for audits.
- Prefer staging or test proxies for first runs.
- Pass secrets through environment variables or hidden prompts instead of shell
  history when possible.
- Avoid sharing `report-*.json`, `forensics.log`, debug output, or capture files
  outside the trusted incident or platform team.
- Review artifacts before attaching them to issues, tickets, pull requests, CI logs,
  or chat threads.
- Store reports and captures with the same access controls used for other production
  diagnostics.
- Rotate audit keys after incident debugging if artifacts were widely shared.

## Safe Logging Guidance

- Keep default logging unless investigating a specific issue.
- Use `--debug` only for local troubleshooting or controlled CI jobs.
- Prefer `--debug-format json` when logs need machine parsing, then apply the same
  retention controls as other sensitive logs.
- Do not paste full debug output into public issues without review.
- Do not add new logging of request headers, request bodies, raw prompts, raw
  response bodies, or unbounded streaming chunks.

## Replay Artifact Handling

- Treat capture files as sensitive by default.
- Store captures in a private location with limited retention.
- Do not upload captures to public issue trackers.
- Prefer sharing a minimal redacted excerpt when reporting bugs.
- Delete local captures after the incident or compatibility investigation is closed
  unless retention is required.
- Remember that `aipf replay` is offline, but the file being replayed may still
  contain sensitive metadata.
