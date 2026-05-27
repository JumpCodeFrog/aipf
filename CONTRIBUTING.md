# CONTRIBUTING.md

## Быстрый старт

Требуется Python 3.11+.

```bash
pipx install -e .
pipx inject aipf pytest pytest-asyncio respx ruff mypy
```

Проверки из pipx venv:

```bash
PIPX_AIPF_BIN=$(pipx environment --value PIPX_LOCAL_VENVS)/aipf/bin
"$PIPX_AIPF_BIN/pytest" -v
"$PIPX_AIPF_BIN/ruff" check src tests
"$PIPX_AIPF_BIN/mypy"
```

Альтернатива для локальной editable-среды допустима, если результат запускает те же `pytest`, `ruff` и `mypy`.

## Конфигурация

Скопируйте `.env.example` в `.env` и заполните:

```env
AIPF_BASE_URL=https://your-proxy.example.com
AIPF_API_KEY=sk-your-key
AIPF_TIMEOUT=90
AIPF_MODEL=your-model-id
AIPF_API_STYLE=auto
AIPF_LATENCY_ROUNDS=5
```

`.env`, logs и reports не коммитятся.

## Правила изменения кода

- Изменения должны быть минимальными и привязанными к задаче.
- Сначала ищите существующий паттерн в соседних модулях.
- Не смешивайте feature, refactor и formatting-only изменения в одной правке.
- Не добавляйте новые runtime dependencies без явной пользы и тестового покрытия.
- Не меняйте формат JSON report без миграционной заметки и тестов.
- Не меняйте exit codes без обновления README и тестов.

## Добавление новой проверки

1. Создайте `src/aipf/checks/<name>.py`.
2. Экспортируйте `NAME = "<name>"`.
3. Реализуйте `async def run(client: AsyncProxyClient, ctx: RunContext)`.
4. Добавьте result model в `src/aipf/models.py`, если существующие модели не подходят.
5. Обновите `TestResult`, `TestResultUnion`, `CHECK_REGISTRY` и `CHECK_ORDER`.
6. Добавьте CLI-команду в `src/aipf/cli.py`, если check должен запускаться отдельно.
7. Покройте:
   - unit-тестом pure logic;
   - integration-тестом с `respx`;
   - CLI help или end-to-end тестом, если добавлена команда.

## Тестирование

Минимум перед сдачей:

```bash
pytest
ruff check src tests
mypy
```

HTTP-тесты должны использовать `respx`.
Не допускайте реальных запросов к OpenAI, Anthropic или production proxy из automated tests.

## CI

GitHub Actions workflow `.github/workflows/ci.yml` запускается на `pull_request` и push в
`main`/`master`.

Pipeline намеренно небольшой:

- Python `3.11` как минимальная поддерживаемая версия из `pyproject.toml`;
- editable install: `python -m pip install -e ".[dev]"`;
- pip dependency cache по `pyproject.toml`;
- `python -m pytest -q`;
- `python -m ruff check src tests --output-format=concise`;
- `python -m mypy --no-error-summary`.

CI не требует secrets и не должен выполнять реальные HTTP-запросы.

### Dependency lock strategy

Сейчас зависимости описаны в `pyproject.toml` диапазонами версий, без lock-файла. Это сохраняет
легкий editable/pipx workflow, но не дает полностью воспроизводимого dependency graph.

Рекомендуемый следующий шаг, когда проекту понадобится жесткая воспроизводимость:

1. Выбрать один инструмент lock management (`uv` предпочтителен для легкого Python CLI; `pip-tools`
   тоже подходит, если нужен только compiled requirements).
2. Закоммитить lock-файл (`uv.lock` или `requirements-dev.txt`).
3. Перевести CI install на locked sync/install.
4. Добавить scheduled dependency refresh отдельным PR-процессом.

Poetry сейчас не нужен: он заметно меняет packaging/dev workflow для небольшого CLI.

## Release hygiene

Базовый release process пока ручной:

1. Обновить `version` в `pyproject.toml` и `src/aipf/__init__.py`.
2. Запустить локально `pytest`, `ruff check src tests`, `mypy`.
3. Проверить, что `.env`, `*.log`, `report-*.json`, `dist/` и `build/` не попали в commit.
4. Создать annotated tag `vX.Y.Z` только после зеленого CI.
5. Для будущей публикации добавить отдельный workflow, который собирает wheel/sdist и публикует
   только из trusted tag без runtime API secrets.

## Style

- Python 3.11 typing syntax: `str | None`, `list[str]`.
- `from __future__ import annotations` в Python-модулях.
- `ruff` line length: 100.
- `mypy` strict.
- Pydantic-модели результатов - strict, без extra fields.
- Ошибки внешних HTTP calls не должны ронять весь CLI без понятного `CheckStatus.ERROR`.

## Security

- Никогда не печатайте API key.
- Не сохраняйте полные prompt/response payloads в logs без redaction review.
- Reports могут содержать response snippets. Считайте их чувствительными артефактами.
- При изменении `logging_setup.py`, `client.py`, `reporter.py` обязательно обновляйте risk review.

## Документация

Если меняется behavior, обновите минимум один из файлов:

- `README.md` - пользовательские команды и install/run flow.
- `ARCHITECTURE.md` - architecture/data flow/API flow.
- `docs/backend-map.md` - карта модулей.
- `docs/risk-zones.md` - новые риски или mitigations.
