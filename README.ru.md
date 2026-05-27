# aipf — API Proxy Forensics Toolkit

[English README](README.md)

`aipf` — асинхронный CLI для forensic-аудита LLM proxy API, совместимых с
OpenAI и Anthropic. Инструмент помогает понять, какие модели отдаёт proxy, как
работают completion и streaming, где возникают retry, похож ли proxy на OpenAI
или Anthropic API, и можно ли воспроизвести debug timeline без повторных HTTP
запросов.

Проект намеренно остаётся небольшим: без сервера, базы данных, web UI и daemon.
Основной интерфейс — терминальный инструмент для локальной диагностики, CI smoke
checks и incident/debug workflows.

## Когда использовать

`aipf` полезен, если нужно:

- проверить OpenAI/Anthropic-compatible proxy перед интеграцией;
- сравнить staging и production proxy;
- понять, почему provider-style auto-detection выбрал не тот режим;
- проверить streaming и non-streaming поведение;
- поймать wrapper leaks, tool-call identifiers и provider fingerprints;
- сохранить sanitized capture и replay-нуть timeline офлайн;
- получить JSON report для автоматизации.

Не используйте `aipf` как proxy server, SDK, load tester, policy engine или model
eval framework. Это focused CLI для API forensics.

## Быстрый старт

Требуется Python 3.11+.

Из исходников:

```bash
git clone <repo-url>
cd aipf
pipx install -e .
```

После первого PyPI release:

```bash
pipx install aipf
```

Самый простой запуск:

```bash
aipf
```

В обычном терминале откроется главное меню. В CI/non-interactive режиме `aipf`
просто покажет help и выйдет, чтобы не зависать на prompt.

Навигация в меню:

- `Enter` выбирает действие по умолчанию;
- `b` или `back` возвращает назад;
- `0` возвращает из submenu или выходит из главного меню;
- `q`, `quit` или `exit` завершает CLI.

## Конфигурация

Минимально нужны endpoint, API key и model:

```env
AIPF_BASE_URL=https://your-proxy.example.com
AIPF_API_KEY=sk-...
AIPF_MODEL=gpt-test
AIPF_API_STYLE=auto
```

Полный аудит:

```bash
aipf run --output report.json
```

Или без env:

```bash
aipf run \
  --base-url https://your-proxy.example.com \
  --api-key "$AIPF_API_KEY" \
  --model gpt-test \
  --api-style auto \
  --output report.json
```

Если модели неизвестны, начните с:

```bash
aipf models \
  --base-url https://your-proxy.example.com \
  --api-key "$AIPF_API_KEY"
```

## Основные команды

```bash
aipf run
aipf interactive
aipf models
aipf completion --model gpt-test
aipf stream --model gpt-test
aipf inject --model gpt-test
aipf leaks --model gpt-test
aipf fingerprint --model gpt-test
aipf tool-ids --model gpt-test
aipf latency --model gpt-test --latency-rounds 10
```

## Debug mode

Debug mode пишет redacted lifecycle events в stderr и не меняет JSON report schema.
Он не логирует request headers, request payloads или raw response bodies.

```bash
aipf completion --model gpt-test --debug
aipf completion --model gpt-test --debug-format json --debug
```

Пример:

```text
trace +0.19ms model.resolve check=completion source=settings model=gpt-test
trace +5.37ms client.init base_url=https://mock.example.com declared_style=openai timeout_s=90
trace +5.63ms http.request.start trace_id=req-d728b0312da method=POST url=https://mock.example.com/v1/chat/completions attempt=1 stream=false
trace +6.42ms http.retry trace_id=req-d728b0312da next_attempt=2 sleep_s=0.0 reason=retry-after status=429
```

## Capture / Replay

Capture сохраняет sanitized forensic timeline. Replay показывает timeline без
реальных HTTP запросов.

```bash
aipf completion --model gpt-test --capture capture.json
aipf replay capture.json
aipf replay capture.json --format json
```

Capture files versioned и deterministic. По умолчанию они не сохраняют raw prompts,
request bodies, request headers, API keys или raw response bodies. Metadata всё
равно может быть чувствительной: target URLs, model names, provider style, timing,
status codes и retry behavior. Обращайтесь с capture/report/log файлами как с
операционными артефактами.

Подробнее: [docs/capture-replay.md](docs/capture-replay.md) и [SECURITY.md](SECURITY.md).

## Что проверяет aipf

| Area | Проверка | Output |
| --- | --- | --- |
| Models | `/v1/models`, model IDs | `models_list` |
| Completion | non-streaming response extraction | `completion` |
| Streaming | SSE shape, chunks, first chunk timing | `streaming` |
| Prompt injection | small prompt-injection battery | `injection` |
| Wrapper leaks | known leak phrases and snippets | `leaks` |
| Provider fingerprint | OpenAI/Anthropic response patterns | `fingerprint` |
| Tool IDs | `toolu_`, `call_` identifiers | `tool_ids` |
| Latency | sequential timing stats | `latency` |
| Capture/replay | offline sanitized timeline | schema-versioned capture |

## Provider support

| Provider style | Endpoint | Auth |
| --- | --- | --- |
| OpenAI-compatible | `/v1/chat/completions` | `Authorization: Bearer ...` |
| Anthropic-compatible | `/v1/messages` | `x-api-key`, `anthropic-version` |
| Auto-detect | `/v1/models` probe | combined probe headers |

Auto-detection conservative: если model IDs выглядят Anthropic-only, используется
Anthropic adapter; иначе fallback — OpenAI-style. Можно явно задать
`--api-style openai` или `--api-style anthropic`.

## Reports и exit codes

`aipf run` пишет:

- JSON report, по умолчанию `aipf-artifacts/reports/report-<timestamp>.json`;
- structured JSON logs, по умолчанию `aipf-artifacts/logs/forensics.log`;
- optional debug trace через `--debug`;
- optional sanitized capture через `--capture`.

`--artifacts-dir PATH` складывает default artifacts в `PATH/reports`,
`PATH/logs` и `PATH/captures`. Явные `--output`, `--log-file` и `--capture`
пишут ровно в указанные пути.

Exit codes:

- `0` — warning/error нет;
- `1` — есть хотя бы один `error`;
- `2` — warning без errors.

JSON report — strict Pydantic contract. Debug traces и capture files не являются
частью `RunReport`.

## Security boundaries

`aipf` ограничивает диагностический вывод, но не является DLP-системой:

- known API key fields, bearer tokens, `Authorization`, `x-api-key` проходят redaction;
- request headers и request bodies не логируются по умолчанию;
- raw response bodies не логируются на INFO;
- capture files хранят sanitized metadata only;
- replay не делает HTTP requests;
- reports могут содержать response snippets от target proxy.

Redaction — защитный слой, а не гарантия отсутствия секретов.

## Разработка

```bash
pipx inject aipf pytest pytest-asyncio respx ruff mypy
PIPX_AIPF_BIN=$(pipx environment --value PIPX_LOCAL_VENVS)/aipf/bin
"$PIPX_AIPF_BIN/pytest"
"$PIPX_AIPF_BIN/ruff" check src tests
"$PIPX_AIPF_BIN/mypy"
```

Правила проекта:

- outbound HTTP только через `src/aipf/client.py`;
- async HTTP client — `httpx.AsyncClient`;
- новые checks добавляются в `src/aipf/checks/` и регистрируются явно;
- `RunReport` менять осторожно;
- HTTP tests — через `respx`, без реальных сетевых вызовов.

Архитектура: [ARCHITECTURE.md](ARCHITECTURE.md), [docs/backend-map.md](docs/backend-map.md).

## License

MIT. См. [LICENSE](LICENSE).

Автор и maintainer: JumpCodeFrog.
