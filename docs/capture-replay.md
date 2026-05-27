# Capture / Replay

## Назначение

Capture / Replay нужен для воспроизводимого forensic debugging без повторных HTTP
запросов к proxy. Capture сохраняет sanitized timeline событий, а replay читает
этот файл и отображает его в human или JSON-lines формате.

## Команды

Создать capture:

```bash
aipf completion --model gpt-test --capture capture.json
aipf run --output report.json --capture capture.json
aipf run --artifacts-dir audit-2026-05-27
```

Воспроизвести capture без сети:

```bash
aipf replay capture.json
aipf replay capture.json --format json
```

Если задан `--artifacts-dir`, default capture пишется в
`<dir>/captures/capture.json`. Без `--artifacts-dir` capture создается только при
явном `--capture`.

## Schema

Текущая версия: `schema_version: 1`.

Top-level fields:

- `schema_version` - версия схемы capture file.
- `meta` - metadata capture session.
- `events` - ordered timeline событий.

`meta`:

- `tool`, `tool_version`, `python_version`;
- `started_at`, `finished_at`;
- `command`;
- `event_count`;
- `truncated`;
- `max_events`, `max_bytes`;
- `notes`.

`event`:

- `seq` - deterministic monotonic sequence number.
- `t_ms` - elapsed milliseconds from capture start.
- `event` - event name, например `http.request.start`, `http.retry`,
  `provider.selection.infer`, `stream.chunk`, `latency.round.end`.
- `fields` - sanitized event metadata.

## Safety Guarantees

- Capture не сохраняет raw prompt, request body, request headers или raw response body.
- API keys и bearer tokens проходят через redaction перед записью.
- Streaming chunks представлены bounded metadata: index, text length, first chunk timing,
  sanitized event lines where applicable.
- Serialization deterministic: JSON пишется с `sort_keys=True`, `indent=2`.
- File size bounded: default `max_events=20000`, `max_bytes=5000000`.
- При превышении лимитов добавляется `capture.truncated`.
- Replay не создает `AsyncProxyClient` и не выполняет HTTP requests.
- Capture schema не является `RunReport` и не меняет JSON report contract.

## Compatibility

В рамках `schema_version=1` новые optional event fields могут добавляться без breaking
change. Breaking changes требуют увеличения `schema_version`.

Consumers должны:

- игнорировать неизвестные event names;
- игнорировать неизвестные fields;
- проверять `schema_version`;
- учитывать `meta.truncated`.

## Future Extension Points

- Optional explicit capture sampling controls.
- Optional capture compression outside core runtime.
- Offline diff between two captures.
- Provider-specific replay summaries.
- Controlled opt-in storage of additional sanitized artifacts after security review.
