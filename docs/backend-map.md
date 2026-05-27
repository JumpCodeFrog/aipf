# Backend Map

В проекте нет web backend в классическом смысле. Backend layer здесь - CLI orchestration, HTTP client, checks, models, reports и logging.

## Package layout

```text
src/aipf/
  __init__.py
  __main__.py
  cli.py
  config.py
  client.py
  models.py
  prompts.py
  fingerprints.py
  scanning.py
  reporter.py
  logging_setup.py
  debug_trace.py
  capture.py
  checks/
    __init__.py
    base.py
    models_list.py
    completion.py
    streaming.py
    injection.py
    leaks.py
    fingerprint.py
    tool_ids.py
    latency.py
```

## `cli.py`

Ответственность:

- объявляет `click` group и commands;
- собирает `Settings` из CLI flags/env;
- создает `AsyncProxyClient`;
- запускает checks;
- пишет report;
- возвращает process exit code.

Важные команды:

- `run`
- `interactive`
- `models`
- `completion`
- `stream`
- `inject`
- `leaks`
- `fingerprint`
- `tool-ids`
- `latency`
- `replay`

Риски:

- файл уже крупный относительно остального проекта;
- CLI flow смешивает UX, orchestration и finalization;
- любые изменения exit codes должны быть покрыты tests.

## `config.py`

Ответственность:

- `Settings` на базе `pydantic-settings`;
- env prefix `AIPF_`;
- `.env` support;
- `base_url_normalized`.

Важные поля:

- `base_url`
- `api_key`
- `timeout_s`
- `model`
- `api_style`
- `latency_rounds`

Риски:

- несоответствие env names и CLI option names;
- чтение реального `.env` в тестах, поэтому `tests/conftest.py` изолирует env и cwd.

## `client.py`

Ответственность:

- lifecycle `httpx.AsyncClient`;
- style detection;
- auth headers;
- OpenAI/Anthropic request payloads;
- bounded retry для transient non-streaming failures;
- streaming parser;
- extraction text из responses.

Важные constants:

- `DEFAULT_MAX_TOKENS = 512`
- `ANTHROPIC_VERSION = "2023-06-01"`
- `RETRY_STATUSES = {408, 429, 500, 502, 503, 504}`
- `MAX_RETRIES = 2`
- `BACKOFF_BASE_MS = 250`
- `MAX_RETRY_SLEEP_S = 30.0`

Риски:

- auto-detection может ошибаться на смешанных model IDs;
- stream parsing сейчас line-oriented и покрывает базовые SSE patterns;
- retry поддерживает bounded exponential backoff и `Retry-After`, но без jitter;
- streaming deliberately single-attempt, чтобы не дублировать частичный SSE output;
- request body не логируется, что хорошо для security, но усложняет диагностику.

## `models.py`

Ответственность:

- enums;
- strict Pydantic result models;
- report schema;
- discriminated union `TestResult`.

Ключевые модели:

- `HttpCallLog`
- `LeakFinding`
- `ProviderFingerprint`
- `ModelsListResult`
- `CompletionResult`
- `StreamingResult`
- `InjectionResult`
- `LeakResult`
- `FingerprintResult`
- `ToolIdResult`
- `LatencyResult`
- `RunMeta`
- `RunReport`

Риски:

- schema является публичным контрактом reports;
- есть модели impersonation, но соответствующая check-команда сейчас не зарегистрирована.

## `checks/`

Общий контракт:

```python
NAME = "check_name"

async def run(client: AsyncProxyClient, ctx: RunContext) -> ResultModel:
    ...
```

### `models_list.py`

Проверяет `/v1/models`.
`passed` если status 2xx и есть model IDs.
`warning` если 2xx, но IDs пустые.
`failed` если HTTP status не 2xx.

### `completion.py`

Проверяет обычный chat completion через prompt `Hello`.
`passed` если 2xx и есть extracted text.

### `streaming.py`

Проверяет SSE streaming.
`passed` если есть `data:` или `event:` формат и chunk count больше 0.

### `injection.py`

Запускает `INJECTION_BATTERY`.
`warning` если найдены leak phrases.
`error` если были exceptions и leak findings не обнаружены.

### `leaks.py`

Отдельно запускает system prompt extraction prompt и ищет leak phrases.

### `fingerprint.py`

Задает identity prompt и считает provider fingerprint по фразам.
Сейчас всегда возвращает `passed`, даже если verdict `unknown`.

### `tool_ids.py`

Ищет `toolu_` и `call_` identifiers в ответе на tools prompt.
`warning` при matches.

### `latency.py`

Делает `latency_rounds` коротких запросов, считает min/max/mean/median/p95/stddev.

## `scanning.py`

Pure logic:

- `snippet`
- `scan_phrases`
- `compute_fingerprint`
- `scan_tool_ids`

Эти функции легко тестировать без HTTP.

## `reporter.py`

Ответственность:

- собрать meta;
- записать JSON report;
- определить exit code.

Риск:

- reports могут содержать response snippets, которые пользователь должен считать чувствительными.

## `logging_setup.py`

Ответственность:

- root logger setup;
- Rich stderr logs;
- JSON file logs;
- `RedactFilter`.

Риск:

- redaction покрывает known fields и bearer в message, но не является полноценным DLP.

## `debug_trace.py`

Ответственность:

- no-op / console / tee trace emitters;
- human и JSON debug event rendering;
- redaction перед выводом debug events.

## `capture.py`

Ответственность:

- `CaptureFile` schema versioning;
- bounded sanitized event collection;
- deterministic capture JSON write;
- replay renderers для human и JSON-lines output.

Риски:

- capture files не должны содержать raw prompt/body/header/response data;
- replay не должен создавать HTTP client или делать network calls.

## Tests map

```text
tests/unit/
  test_cli_help.py
  test_models.py
  test_reporter.py
  test_scanning.py

tests/integration/
  test_client_openai.py
  test_client_anthropic.py
  test_run_end_to_end.py
```

`tests/conftest.py` изолирует env, cwd и дает fixtures для OpenAI/Anthropic responses.
