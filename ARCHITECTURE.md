# ARCHITECTURE.md

## Назначение

`aipf` - async CLI-инструмент для forensic-аудита LLM proxy API, совместимых с OpenAI Chat Completions и Anthropic Messages API.
Инструмент проверяет доступность моделей, completion, streaming, prompt injection, wrapper leaks, provider fingerprint, tool IDs и latency.

Это не серверное приложение. В репозитории нет frontend, базы данных, фоновых worker'ов, очередей или Docker-контура.

## Стек

- Python `>=3.11`.
- `httpx` - async HTTP-клиент.
- `pydantic` и `pydantic-settings` - строгие модели результатов и конфигурация через env.
- `click` - CLI.
- `rich` - вывод таблиц, JSON и логов.
- `python-json-logger` - structured JSON logs.
- `pytest`, `pytest-asyncio`, `respx` - тесты и HTTP mocks.
- `ruff`, `mypy strict` - style/static checks.
- `hatchling` - build backend.

## Главные entrypoints

- `aipf` console script из `pyproject.toml`, указывает на `aipf.cli:main`.
- `python -m aipf`, через `src/aipf/__main__.py`.
- `run-aipf-interactive.sh` и `run-aipf-interactive.bat` - desktop-friendly launchers для интерактивного режима.

## Высокоуровневая схема

```text
CLI command
  -> Settings
  -> optional debug tracer
  -> optional capture tracer
  -> AsyncProxyClient
  -> provider style detection
  -> check registry / check order
  -> Pydantic result models
  -> RunReport
  -> JSON report + structured logs + exit code
```

## Модули

- `src/aipf/cli.py`
  Управляет CLI-командами, опциями, интерактивным выбором модели, запуском checks, финализацией report и exit codes.

- `src/aipf/config.py`
  Загружает `AIPF_*` настройки через `BaseSettings`. API key хранится как `SecretStr`.

- `src/aipf/client.py`
  Единственный HTTP adapter. Инкапсулирует auth headers, provider style detection, OpenAI/Anthropic payloads, bounded retry для transient non-streaming failures, streaming parsing и extraction response text.

- `src/aipf/checks/`
  Отдельные check modules. Каждый модуль экспортирует `NAME` и async `run(client, ctx)`.

- `src/aipf/models.py`
  Контракт JSON reports. Pydantic-модели строгие: `extra="forbid"`, discriminator по `kind`.

- `src/aipf/prompts.py`
  Prompt battery и базовые prompts.

- `src/aipf/fingerprints.py`
  Константы эвристик: leak phrases, provider phrases, tool ID prefixes.

- `src/aipf/scanning.py`
  Pure functions для поиска leak phrases, provider fingerprints, tool IDs и snippets.

- `src/aipf/reporter.py`
  Формирование `RunReport`, запись JSON и расчет exit code.

- `src/aipf/logging_setup.py`
  Rich logging, JSON file logging и redaction filter.

- `src/aipf/debug_trace.py`
  Отдельный opt-in debug trace layer для CLI. По умолчанию no-op; в `--debug`
  режиме пишет redacted human или JSON lifecycle events в stderr, не меняя
  `RunReport`.

- `src/aipf/capture.py`
  Версионированная Capture / Replay схема и рендеринг timeline. Capture сохраняет
  только sanitized trace metadata, ограничивает размер файла и не является частью
  `RunReport`.

## API flow

### Provider style

Если `AIPF_API_STYLE=auto`, клиент делает `GET /v1/models` с комбинированными OpenAI и Anthropic auth headers:

- `Authorization: Bearer <key>`
- `x-api-key: <key>`
- `anthropic-version: 2023-06-01`

Если payload моделей содержит только `claude` или `anthropic` IDs, стиль считается `anthropic`; иначе fallback - `openai`.

### OpenAI flow

- Models: `GET /v1/models`
- Chat: `POST /v1/chat/completions`
- Payload: `model`, `messages`, `max_tokens`, `stream`
- Auth: `Authorization: Bearer <api_key>`

### Anthropic flow

- Models: `GET /v1/models`
- Messages: `POST /v1/messages`
- Payload: `model`, `messages`, `max_tokens`, `stream`
- Auth: `x-api-key`, `anthropic-version`

## Check flow

`CHECK_ORDER` сейчас:

1. `models_list`
2. `completion`
3. `streaming`
4. `injection`
5. `leaks`
6. `fingerprint`
7. `tool_ids`
8. `latency`

Каждая проверка возвращает один из типов `TestResultUnion`.
Статусы: `passed`, `failed`, `warning`, `error`, `skipped`.

## Report flow

`aipf run` по умолчанию пишет:

- `report-<timestamp>.json`
- `forensics.log`
- optional stderr debug trace через `--debug` / `--trace`
- optional sanitized capture file через `--capture`

Exit codes:

- `0` - все проверки passed.
- `1` - есть хотя бы один `error`.
- `2` - есть warning без errors.

## Data flow

```text
User input / env / CLI flags
  -> Settings
  -> optional debug tracer
  -> optional capture tracer
  -> AsyncProxyClient
  -> HTTP calls to proxy
  -> response text / streaming chunks
  -> scanning and heuristics
  -> Pydantic results
  -> report JSON
```

Replay flow:

```text
capture JSON file
  -> CaptureFile validation
  -> human or JSON-lines timeline rendering
```

Replay не создает HTTP client и не выполняет сетевые запросы.

## Auth flow

Проект не реализует собственную аутентификацию пользователей. Он принимает API key целевого proxy через:

- `AIPF_API_KEY` в `.env` или окружении.
- `--api-key`.
- скрытый prompt в `aipf interactive`.

API key используется только для outbound requests. Он не должен попадать в logs или reports.

## База данных

Базы данных нет. Состояние не хранится между запусками, кроме JSON reports и log files.

## Frontend

Frontend отсутствует. Пользовательский интерфейс - CLI на `click` и `rich`.

## Docker

Dockerfile и compose-конфигурация отсутствуют.
Текущий recommended install path - `pipx install -e .`.

## CI/CD

Минимальный GitHub Actions pipeline находится в `.github/workflows/ci.yml`.
Он запускает editable install с `.[dev]`, затем `pytest`, `ruff` и `mypy`.
