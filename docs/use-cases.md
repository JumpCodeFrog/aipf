# Use Cases

## 1. Proxy Compatibility Check

Use when introducing a new LLM gateway, hosted proxy, vendor router, or internal
compatibility layer.

Command:

```bash
aipf run --base-url https://proxy.example.com --model gpt-test --output report.json
```

What to inspect:

- `models_list` result for model visibility;
- `completion` and `streaming` result consistency;
- `fingerprint` result for provider-style hints;
- `latency` stats for obvious degradation;
- exit code for CI gating.

## 2. Provider Style Debugging

Use when a proxy claims OpenAI compatibility but behaves like Anthropic, or when
auto-detection chooses the wrong path.

Commands:

```bash
aipf models --api-style auto --debug
aipf completion --api-style openai --model gpt-test --debug
aipf completion --api-style anthropic --model claude-test --debug
```

What to inspect:

- `provider.selection.*` debug events;
- request endpoint paths;
- response status codes;
- model IDs from `/v1/models`.

## 3. Streaming Regression

Use when streaming fails after a gateway update, SDK migration, or provider switch.

Command:

```bash
aipf stream --model gpt-test --capture stream-capture.json
aipf replay stream-capture.json
```

What to inspect:

- `stream.request.build`;
- `http.response.headers`;
- `stream.chunk`;
- `stream.chunk.done`;
- first chunk timing and total chunk count.

## 4. Retry and Rate Limit Analysis

Use when users report intermittent failures that disappear on retry.

Command:

```bash
aipf completion --model gpt-test --debug --capture retry-capture.json
```

What to inspect:

- `http.request.end` status codes;
- `http.retry` events;
- retry reasons such as `retry-after`, `http_429`, `http_503`;
- per-attempt latency.

## 5. Wrapper Leak Audit

Use when testing whether a proxy or wrapper reveals implementation details.

Commands:

```bash
aipf leaks --model gpt-test --output leaks-report.json
aipf inject --model gpt-test --output injection-report.json
```

What to inspect:

- `LeakFinding` phrases;
- context snippets in the JSON report;
- warning exit code.

Reports can contain response snippets. Treat them as sensitive operational artifacts.

## 6. CI Smoke Test

Use when a staging proxy must remain compatible before deploy.

Example CI step:

```bash
aipf run \
  --base-url "$AIPF_BASE_URL" \
  --api-key "$AIPF_API_KEY" \
  --model "$AIPF_MODEL" \
  --output aipf-report.json
```

Exit code contract:

- `0` - no warnings/errors;
- `1` - errors;
- `2` - warnings without errors.

Teams can decide whether warning exit code `2` should fail or only annotate CI.

## 7. Incident Timeline Capture

Use when a proxy has a transient production issue and you need a portable debugging
artifact.

Command:

```bash
aipf run --model gpt-test --artifacts-dir incident-audit
```

Share:

- `incident-audit/reports/report-*.json` for check results;
- `incident-audit/captures/capture.json` for timeline replay;
- `incident-audit/logs/forensics.log` if structured logs are needed.

Do not share API keys or raw proxy payloads. Capture files are sanitized, but still
review them before sending outside your organization.

## 8. Vendor Evaluation

Use when comparing proxy vendors or provider abstraction layers.

Run the same commands against each endpoint:

```bash
aipf run --base-url https://vendor-a.example.com --model gpt-test --output vendor-a.json
aipf run --base-url https://vendor-b.example.com --model gpt-test --output vendor-b.json
```

Compare:

- endpoint compatibility;
- provider fingerprints;
- streaming behavior;
- latency stats;
- leak warnings;
- tool ID patterns.

## 9. Local Development Loop

Use while developing a new proxy or adapter.

Workflow:

```bash
aipf models --base-url http://localhost:8080 --api-key dev
aipf completion --base-url http://localhost:8080 --api-key dev --model test --debug
aipf stream --base-url http://localhost:8080 --api-key dev --model test --capture stream.json
```

This keeps the feedback loop focused on protocol behavior without adding a browser,
database, or daemon.

## Not a Fit

`aipf` is not the right tool when you need:

- high-volume load testing;
- model quality evaluation;
- production metrics dashboards;
- long-running monitoring;
- request/response traffic interception;
- policy enforcement;
- prompt-injection prevention guarantees.

Those are separate tool categories. `aipf` can complement them by producing
structured forensic evidence for a specific proxy endpoint.
