# CLI Branding

## Цель

`aipf` должен выглядеть как спокойный production-grade security tool для LLM infrastructure:
чистый, узнаваемый, быстрый и пригодный для CI/pipe-сценариев.

## UX-аудит до redesign

- Startup output был почти отсутствующим: пользователь сразу видел отдельные строки progress без контекста запуска.
- Errors печатались компактно, но без общей визуальной системы статусов.
- Progress использовал простые строки `▶ check_name`, из-за чего long run плохо сканировался.
- Summary был одной длинной строкой; на узких терминалах читался хуже.
- Report rendering через JSON report не требовал изменений, но сообщение о path было слишком общее.
- Colors были минимальными и не формировали стабильную severity-семантику.
- Streaming output не выводит raw chunks, что правильно для безопасности и стабильности UX.

## Visual Direction

- Brand signal: компактный ASCII logo `aipf`, без heavy art и без unreadable gradients.
- Tone: security tooling + LLM infrastructure + async/cyberpunk minimalism.
- Primary accent: cyan для инструмента и активного аудита.
- Provider badges:
  - `openai` - green;
  - `anthropic` - magenta;
  - `auto` - cyan.
- Severity colors:
  - `passed` - green;
  - `warning` - yellow;
  - `failed` - red;
  - `error` - bold red;
  - `skipped` - dim.
- Layout:
  - `run` и `interactive` получают startup banner;
  - progress выводится как компактные numbered rows;
  - summary выводится отдельной таблицей в TTY и plain-line в non-TTY;
  - single-check commands сохраняют JSON-first output.

## Rendering Rules

- Не использовать Textual, curses или heavy TUI.
- Не добавлять runtime dependencies сверх уже используемого `rich`.
- Не использовать live spinners в non-TTY.
- Не печатать secrets, Authorization headers, request payloads или raw responses.
- JSON report schema и exit-code contract не являются частью branding layer и не меняются.
- В pipe/CliRunner вывод должен оставаться deterministic plain text.

## Примеры

Plain/non-TTY режим:

```text
aipf | async LLM proxy audit | mode=run | provider=openai | model=gpt-test | endpoint=https://mock.example.com
running 8 checks | provider=openai
01/08 RUN MODELS
01/08 [PASS] MODELS 12ms 2 model(s)
02/08 RUN COMPLETION
02/08 [PASS] COMPLETION 35ms 3 token est.
report=report.json
summary | model=gpt-test | provider=openai | passed=8 | warning=0 | failed=0 | error=0 | skipped=0
```

TTY режим использует тот же порядок и данные, но добавляет border panel, Unicode status symbols
и compact tables. Это cosmetic layer; report JSON остается машинным контрактом.
