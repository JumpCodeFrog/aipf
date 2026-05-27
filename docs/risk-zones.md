# Risk Zones

## High

### Secret leakage in logs or reports

Риск: API key может попасть в stderr, JSON log, report или test output.

Затронутые файлы:

- `src/aipf/client.py`
- `src/aipf/logging_setup.py`
- `src/aipf/reporter.py`
- `src/aipf/cli.py`

Mitigation:

- не логировать request headers и bodies;
- держать `api_key` как `SecretStr` в settings;
- редактировать известные API-key patterns и текущий `AIPF_API_KEY` перед записью logs/reports;
- расширять tests для `RedactFilter` при изменении logging;
- считать `response_snippet` потенциально чувствительным даже после redaction, так как proxy response может содержать не-key секреты.

### Wrong provider style detection

Риск: auto-detection fallback на OpenAI может отправить запрос на неверный endpoint.

Затронутые файлы:

- `src/aipf/client.py`
- `tests/integration/test_client_openai.py`
- `tests/integration/test_client_anthropic.py`

Mitigation:

- покрывать смешанные и нестандартные `/v1/models` payloads;
- добавлять диагностические details в report при detection fallback;
- позволять явный `--api-style`.

### Report schema regression

Риск: downstream tooling может зависеть от JSON report.

Затронутые файлы:

- `src/aipf/models.py`
- `src/aipf/reporter.py`
- `tests/unit/test_models.py`
- `tests/integration/test_run_end_to_end.py`

Mitigation:

- менять schema только через Pydantic models;
- добавлять round-trip tests;
- документировать breaking changes.

## Medium

### Prompt injection false positives

Риск: `scan_phrases` ищет простые substrings. Это удобно, но может давать false positives на отказах модели или объяснениях.

Затронутые файлы:

- `src/aipf/fingerprints.py`
- `src/aipf/scanning.py`
- `src/aipf/checks/injection.py`
- `src/aipf/checks/leaks.py`

Mitigation:

- хранить context snippets;
- добавлять severity/confidence при расширении модели findings;
- тестировать отрицательные примеры.

### Streaming parser coverage

Риск: provider/proxy может использовать SSE variants, которые текущий line parser не извлекает.

Затронутые файлы:

- `src/aipf/client.py`
- `tests/integration/test_client_openai.py`
- `tests/integration/test_client_anthropic.py`

Mitigation:

- добавить fixtures для comments, multiline data, keepalive, non-JSON chunks;
- различать invalid SSE и valid SSE без text delta.

### Retry/backoff behavior

Риск: retry покрывает только non-streaming HTTP calls. Streaming intentionally не retryится,
чтобы не дублировать частичные SSE chunks. Backoff deterministic и bounded, без jitter.

Затронутые файлы:

- `src/aipf/client.py`
- `tests/integration/test_client_openai.py`

Mitigation:

- поддерживать `Retry-After` с upper cap;
- держать `MAX_RETRIES` небольшим и фиксированным;
- тестировать transient/permanent failures и streaming no-retry behavior;
- jitter можно добавить позже только если это не ломает deterministic tests.

### CLI orchestration complexity

Риск: `cli.py` концентрирует settings, UX, checks orchestration, report finalization и exit.

Mitigation:

- новые сложные orchestration paths выносить в маленькие helper-функции;
- не делать большой refactor без отдельной задачи;
- покрывать interactive/non-interactive paths.

## Low

### CI/CD foundation

Риск: CI покрывает базовые проверки, но пока не фиксирует полный dependency graph lock-файлом.

Mitigation:

- GitHub Actions запускает `pytest`, `ruff check src tests`, `mypy`;
- CI использует Python 3.11 как минимальную поддерживаемую версию;
- install path: editable `.[dev]`;
- pip cache keyed by `pyproject.toml`.

### No Docker

Риск: разный local setup у пользователей.

Mitigation:

- пока не добавлять Docker без требования;
- если добавлять, держать image тонким CLI runtime, без secrets baked into image.

### No dependency lock

Риск: floating dependency ranges могут дать несовместимую minor/major transitive версию.

Mitigation:

- для production distribution рассмотреть lock через `uv.lock`, `requirements-dev.txt` или другой принятый инструмент;
- тестировать регулярные dependency upgrades.

## Legacy / technical debt

- В `models.py` есть impersonation-модели, но нет зарегистрированной impersonation check. Это может быть заготовка под будущий feature или недоделанная ветка.
- `aipf-artifacts/`, `forensics.log`, `report-*.json`, `logs/`, `reports/` и `captures/` считаются runtime artifacts и игнорируются `.gitignore`.
- Нет Docker, dependency lock и полноценного release process.

## Potential bottlenecks

- Latency check выполняет rounds последовательно. Это хорошо для замера пользовательского сценария, но медленно при большом `latency_rounds`.
- Injection battery выполняется последовательно. Параллелизм может ускорить прогон, но исказит rate limit и latency картину.
- Streaming parser держит sample chunks и accumulated text в памяти. Сейчас лимиты малы, но при расширении max tokens нужен cap.

## Safe improvement roadmap

1. Добавить dependency lock для reproducible dev setup.
2. Добавить tests для mixed/empty/non-standard `/v1/models`.
3. Расширить streaming parser fixtures.
4. Добавить `Retry-After` support.
5. Решить судьбу impersonation models: удалить как dead code или оформить как check.
6. Добавить release workflow: build wheel/sdist, validate metadata, publish only from tags.
