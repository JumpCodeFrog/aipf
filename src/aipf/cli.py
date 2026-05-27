from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import click
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from aipf.capture import (
    CaptureError,
    CaptureTracer,
    read_capture,
    render_capture_human,
    render_capture_json_lines,
)
from aipf.checks import CHECK_ORDER, CHECK_REGISTRY, RunContext
from aipf.checks.base import TestResultUnion
from aipf.client import AsyncProxyClient
from aipf.config import Settings
from aipf.debug_trace import DebugFormat, DebugTracer, TeeDebugTracer, make_debug_tracer
from aipf.logging_setup import add_sensitive_value, configure
from aipf.models import (
    ApiStyle,
    CheckStatus,
    CompletionResult,
    FingerprintResult,
    InjectionResult,
    LatencyResult,
    LeakResult,
    ModelsListResult,
    StreamingResult,
    ToolIdResult,
)
from aipf.redaction import redact_data, redact_text
from aipf.reporter import (
    CAPTURES_DIR,
    build_report,
    default_log_path,
    default_report_path,
    exit_code_for,
    write_report,
)

stderr_console = Console(stderr=True, highlight=False, soft_wrap=True)
logger = logging.getLogger(__name__)

API_STYLE_CHOICES = ("auto", "openai", "anthropic")
DEBUG_FORMAT_CHOICES = ("human", "json")
REPLAY_FORMAT_CHOICES = ("human", "json")
MAIN_MENU_CHOICES = ("1", "2", "3", "4", "5", "0", "q")
BACK_CHOICES = {"b", "back", "0"}
QUIT_CHOICES = {"q", "quit", "exit"}
NAVIGATION_HINT = "Enter 'b' to go back, 'q' to quit."
MENU_BACK_CODE = 2
PRODUCT_NAME = "API Proxy Forensics Toolkit"
PRODUCT_TAGLINE = "async LLM proxy audit"
DEFAULT_CAPTURE_NAME = "capture.json"
LOGO_LINES = (
    "    ___    ____  ____  ______",
    "   /   |  /  _/ / __ \\/ ____/",
    "  / /| |  / /  / /_/ / /_    ",
    " / ___ |_/ /  / ____/ __/    ",
    "/_/  |_/___/ /_/   /_/       ",
)
CHECK_LABELS = {
    "models_list": "MODELS",
    "completion": "COMPLETION",
    "streaming": "STREAM",
    "injection": "INJECTION",
    "leaks": "LEAKS",
    "fingerprint": "FINGERPRINT",
    "tool_ids": "TOOL IDS",
    "latency": "LATENCY",
}
PROVIDER_STYLES = {
    "auto": "cyan",
    "openai": "green",
    "anthropic": "magenta",
}
STATUS_STYLES = {
    CheckStatus.PASSED: ("PASS", "green", "✓"),
    CheckStatus.WARNING: ("WARN", "yellow", "!"),
    CheckStatus.FAILED: ("FAIL", "red", "×"),
    CheckStatus.ERROR: ("ERR", "bold red", "×"),
    CheckStatus.SKIPPED: ("SKIP", "dim", "-"),
}
REQUIRED_SETTING_HINTS = {
    "base_url": ("proxy base URL", "--base-url", "AIPF_BASE_URL"),
    "api_key": ("API key", "--api-key", "AIPF_API_KEY"),
}


class NavigationExit(Exception):
    def __init__(self, action: str) -> None:
        self.action = action


def _plain_console() -> bool:
    return not stderr_console.is_terminal


def _stdin_is_interactive() -> bool:
    return sys.stdin.isatty()


def _status_meta(status: CheckStatus) -> tuple[str, str, str]:
    return STATUS_STYLES[status]


def _provider_badge(style: ApiStyle | str) -> Text:
    value = style.value if isinstance(style, ApiStyle) else style
    color = PROVIDER_STYLES.get(value, "cyan")
    if _plain_console():
        return Text(f"provider={value}")
    return Text.assemble(
        ("provider", "dim"),
        ("=", "dim"),
        (value, f"bold {color}"),
    )


def _redacted_endpoint(base_url: str, sensitive_values: tuple[str, ...] = ()) -> str:
    redacted = redact_text(base_url, sensitive_values)
    parts = urlsplit(redacted)
    if not parts.scheme or not parts.netloc:
        return redacted
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _check_label(name: str) -> str:
    return CHECK_LABELS.get(name, name.replace("_", " ").upper())


def _print_banner(
    *,
    mode: str,
    settings: Settings,
    output: Path | None,
    log_file: Path | None,
    sensitive_values: tuple[str, ...],
) -> None:
    endpoint = _redacted_endpoint(settings.base_url_normalized, sensitive_values)
    model = redact_text(settings.model or "(pending)", sensitive_values)
    style = (
        settings.api_style.value
        if isinstance(settings.api_style, ApiStyle)
        else settings.api_style
    )

    if _plain_console():
        stderr_console.print(
            f"aipf | {PRODUCT_TAGLINE} | mode={mode} | provider={style} | "
            f"model={model} | endpoint={endpoint}"
        )
        return

    body = Text()
    body.append("\n".join(LOGO_LINES), "bold cyan")
    body.append("\n")
    body.append(PRODUCT_NAME, "bold white")
    body.append("  ")
    body.append(PRODUCT_TAGLINE, "dim")
    body.append("\n\n")
    body.append("mode", "dim")
    body.append(f"={mode}  ", "white")
    body.append("model", "dim")
    body.append(f"={model}  ", "white")
    body.append("endpoint", "dim")
    body.append(f"={endpoint}\n", "white")
    body.append("provider", "dim")
    body.append(f"={style}  ", PROVIDER_STYLES.get(style, "cyan"))
    body.append("timeout", "dim")
    body.append(f"={settings.timeout_s}s  ", "white")
    body.append("latency_rounds", "dim")
    body.append(f"={settings.latency_rounds}", "white")
    if output is not None:
        body.append("\nreport", "dim")
        body.append(f"={output}", "white")
    if log_file is not None:
        body.append("  log", "dim")
        body.append(f"={log_file}", "white")

    stderr_console.print(
        Panel(
            body,
            title="[bold cyan]aipf[/]",
            subtitle="[dim]deterministic CLI audit[/]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _format_duration_ms(duration_ms: float) -> str:
    if duration_ms >= 1000:
        return f"{duration_ms / 1000:.2f}s"
    return f"{duration_ms:.0f}ms"


def _models_signal(result: TestResultUnion) -> str:
    models_result = cast(ModelsListResult, result)
    if models_result.models:
        return f"{len(models_result.models)} model(s)"
    return "no models"


def _completion_signal(result: TestResultUnion) -> str:
    completion_result = cast(CompletionResult, result)
    return f"{completion_result.tokens_estimate} token est."


def _streaming_signal(result: TestResultUnion) -> str:
    streaming_result = cast(StreamingResult, result)
    return f"{streaming_result.chunk_count} chunks"


def _injection_signal(result: TestResultUnion) -> str:
    injection_result = cast(InjectionResult, result)
    findings = sum(len(attempt.triggered_leaks) for attempt in injection_result.attempts)
    return f"{len(injection_result.attempts)} attacks, {findings} signals"


def _leaks_signal(result: TestResultUnion) -> str:
    leak_result = cast(LeakResult, result)
    return f"{len(leak_result.findings)} finding(s)"


def _fingerprint_signal(result: TestResultUnion) -> str:
    fingerprint_result = cast(FingerprintResult, result)
    return f"verdict={fingerprint_result.fingerprint.verdict}"


def _tool_ids_signal(result: TestResultUnion) -> str:
    tool_id_result = cast(ToolIdResult, result)
    match_count = sum(len(matches) for matches in tool_id_result.matches.values())
    return f"{match_count} match(es)"


def _latency_signal(result: TestResultUnion) -> str:
    latency_result = cast(LatencyResult, result)
    if latency_result.stats is None:
        return "no samples"
    return f"p95={latency_result.stats.p95_ms:.0f}ms mean={latency_result.stats.mean_ms:.0f}ms"


RESULT_SIGNAL_BUILDERS = {
    ModelsListResult: _models_signal,
    CompletionResult: _completion_signal,
    StreamingResult: _streaming_signal,
    InjectionResult: _injection_signal,
    LeakResult: _leaks_signal,
    FingerprintResult: _fingerprint_signal,
    ToolIdResult: _tool_ids_signal,
    LatencyResult: _latency_signal,
}


def _result_signal(result: TestResultUnion, sensitive_values: tuple[str, ...]) -> str:
    builder = RESULT_SIGNAL_BUILDERS.get(type(result))
    if builder is not None:
        return builder(result)
    if result.error:
        return redact_text(result.error, sensitive_values)
    return ""


def _print_result_row(
    *,
    index: int,
    total: int,
    result: TestResultUnion,
    sensitive_values: tuple[str, ...],
) -> None:
    label, style, symbol = _status_meta(result.status)
    signal = _result_signal(result, sensitive_values)
    prefix = f"{index:02d}/{total:02d}"
    name = _check_label(result.name)
    if _plain_console():
        stderr_console.print(
            f"{prefix} [{label}] {name} {_format_duration_ms(result.duration_ms)} {signal}"
        )
        return
    line = Text.assemble(
        (prefix, "dim"),
        ("  ", ""),
        (symbol, style),
        (" ", ""),
        (label.ljust(4), f"bold {style}"),
        ("  ", ""),
        (name.ljust(12), "bold white"),
        (" ", ""),
        (_format_duration_ms(result.duration_ms).rjust(7), "dim"),
    )
    if signal:
        line.append("  ")
        line.append(redact_text(signal, sensitive_values), "dim")
    stderr_console.print(line)


def _print_run_header(check_count: int, style: ApiStyle) -> None:
    if _plain_console():
        stderr_console.print(f"running {check_count} checks | provider={style.value}")
        return
    header = Text.assemble(
        ("running ", "dim"),
        (str(check_count), "bold white"),
        (" checks  ", "dim"),
        _provider_badge(style),
    )
    stderr_console.print(header)


def _print_key_value(label: str, value: str, style: str = "white") -> None:
    if _plain_console():
        stderr_console.print(f"{label}={value}")
        return
    stderr_console.print(Text.assemble((label, "dim"), ("=", "dim"), (value, style)))


def _print_notice(message: str, status: CheckStatus = CheckStatus.WARNING) -> None:
    label, style, symbol = _status_meta(status)
    if _plain_console():
        stderr_console.print(f"[{label}] {message}")
        return
    stderr_console.print(Text.assemble((symbol, style), (" ", ""), (message, style)))


def _navigation_action(raw: str) -> str | None:
    lowered = raw.strip().lower()
    if lowered in BACK_CHOICES:
        return "back"
    if lowered in QUIT_CHOICES:
        return "quit"
    return None


def _prompt_with_navigation(
    prompt: str,
    *,
    hide_input: bool = False,
    allow_empty: bool = False,
) -> str:
    while True:
        value = cast(
            str,
            click.prompt(
                f"{prompt} ({NAVIGATION_HINT})",
                type=str,
                hide_input=hide_input,
                default="",
                show_default=False,
            ),
        ).strip()
        action = _navigation_action(value)
        if action is not None:
            raise NavigationExit(action)
        if value or allow_empty:
            return value
        _print_notice("Value cannot be empty. Enter 'b' to go back or 'q' to quit.")


def _settings_from_options(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    api_style: str | None,
    timeout: int | None,
    latency_rounds: int | None,
) -> Settings:
    overrides: dict[str, Any] = {}
    if base_url is not None:
        overrides["base_url"] = base_url
    if api_key is not None:
        overrides["api_key"] = api_key
    if model is not None:
        overrides["model"] = model
    if api_style is not None:
        overrides["api_style"] = api_style
    if timeout is not None:
        overrides["timeout_s"] = timeout
    if latency_rounds is not None:
        overrides["latency_rounds"] = latency_rounds
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        raise click.UsageError(_format_settings_error(exc)) from exc


def _format_settings_error(exc: ValidationError) -> str:
    missing_fields: list[str] = []
    invalid_fields: list[tuple[str, str]] = []
    for error in exc.errors():
        if not error["loc"]:
            continue
        field = str(error["loc"][0])
        if error["type"] == "missing":
            missing_fields.append(field)
        else:
            invalid_fields.append((field, str(error["msg"])))
    if missing_fields:
        lines = ["Missing required configuration:"]
        for field in missing_fields:
            hint = REQUIRED_SETTING_HINTS.get(field)
            if hint is None:
                lines.append(f"  - {field}")
                continue
            label, option, env_var = hint
            lines.append(f"  - {label}: pass {option} or set {env_var}.")
        lines.append("For guided setup, run: aipf interactive")
        return "\n".join(lines)

    lines = ["Invalid configuration:"]
    for field, message in invalid_fields:
        hint = REQUIRED_SETTING_HINTS.get(field)
        if hint is None:
            lines.append(f"  - {field}: {message}")
            continue
        label, option, env_var = hint
        lines.append(f"  - {label}: {message}. Pass {option} or set {env_var}.")
    return "\n".join(lines)


def _require_model(settings: Settings) -> str:
    if not settings.model:
        raise click.UsageError(
            "Model is required for this command. Pass --model or set AIPF_MODEL."
        )
    return settings.model


def _make_client(settings: Settings) -> AsyncProxyClient:
    return _make_client_with_debug(settings, make_debug_tracer(False))


def _make_client_with_debug(
    settings: Settings,
    debug_tracer: DebugTracer,
) -> AsyncProxyClient:
    return AsyncProxyClient(
        base_url=settings.base_url_normalized,
        api_key=settings.api_key.get_secret_value(),
        api_style=settings.api_style,
        timeout_s=settings.timeout_s,
        debug_tracer=debug_tracer,
    )


def _make_trace_bundle(
    *,
    debug: bool,
    debug_format: str,
    capture: Path | None,
    command: str,
    sensitive_values: tuple[str, ...],
) -> tuple[DebugTracer, CaptureTracer | None]:
    debug_tracer = make_debug_tracer(
        debug,
        output_format=cast(DebugFormat, debug_format),
        sensitive_values=sensitive_values,
    )
    if capture is None:
        return debug_tracer, None
    capture_tracer = CaptureTracer(
        command=command,
        sensitive_values=sensitive_values,
    )
    return cast(DebugTracer, TeeDebugTracer(debug_tracer, capture_tracer)), capture_tracer


def _write_capture_if_requested(capture_path: Path | None, tracer: CaptureTracer | None) -> None:
    if capture_path is None or tracer is None:
        return
    capture_file = tracer.write(capture_path)
    if _plain_console():
        stderr_console.print(
            f"capture={capture_path} events={capture_file.meta.event_count} "
            f"truncated={str(capture_file.meta.truncated).lower()}"
        )
        return
    stderr_console.print(
        Text.assemble(
            ("capture", "dim"),
            ("=", "dim"),
            (str(capture_path), "bold cyan"),
            (" events=", "dim"),
            (str(capture_file.meta.event_count), "white"),
            (" truncated=", "dim"),
            (str(capture_file.meta.truncated).lower(), "white"),
        )
    )


def _print_result(result: TestResultUnion, sensitive_values: tuple[str, ...]) -> None:
    payload = redact_data(result.model_dump(mode="json"), sensitive_values)
    stderr_console.print_json(json.dumps(payload, ensure_ascii=False))


def _print_report_written(output: Path) -> None:
    if _plain_console():
        stderr_console.print(f"report={output}")
        return
    stderr_console.print(
        Text.assemble(("report", "dim"), ("=", "dim"), (str(output), "bold green"))
    )


def _finalize(
    settings: Settings,
    results: list[TestResultUnion],
    started_at: datetime,
    output: Path | None,
    style: ApiStyle,
) -> int:
    finished_at = datetime.now(UTC)
    model = settings.model or "(unspecified)"
    sensitive_values = (settings.api_key.get_secret_value(),)
    report = build_report(
        base_url=settings.base_url_normalized,
        model=model,
        api_style=style,
        results=results,
        started_at=started_at,
        finished_at=finished_at,
        sensitive_values=sensitive_values,
    )
    if output is not None:
        write_report(report, output, sensitive_values=sensitive_values)
        _print_report_written(output)
    return exit_code_for(report)


async def _run_named_checks(
    client: AsyncProxyClient,
    ctx: RunContext,
    check_names: Sequence[str],
    sensitive_values: tuple[str, ...] = (),
) -> list[TestResultUnion]:
    results: list[TestResultUnion] = []
    total = len(check_names)
    for index, name in enumerate(check_names, start=1):
        fn = CHECK_REGISTRY[name]
        if _plain_console():
            stderr_console.print(f"{index:02d}/{total:02d} RUN {_check_label(name)}")
        else:
            stderr_console.print(
                Text.assemble(
                    (f"{index:02d}/{total:02d}", "dim"),
                    ("  ", ""),
                    ("◌", "cyan"),
                    (" RUN   ", "bold cyan"),
                    (_check_label(name), "bold white"),
                )
            )
        result = await fn(client, ctx)
        results.append(result)
        _print_result_row(
            index=index,
            total=total,
            result=result,
            sensitive_values=sensitive_values,
        )
    return results


async def _run_full(settings: Settings, output: Path | None) -> int:
    model = _require_model(settings)
    started_at = datetime.now(UTC)
    sensitive_values = (settings.api_key.get_secret_value(),)
    async with _make_client(settings) as client:
        style = await client.ensure_style()
        _print_run_header(len(CHECK_ORDER), style)
        ctx = RunContext(model=model, latency_rounds=settings.latency_rounds)
        results = await _run_named_checks(client, ctx, CHECK_ORDER, sensitive_values)
        style = client.style
    code = _finalize(settings, results, started_at, output, style)
    _print_summary(results, model, style, sensitive_values)
    return code


async def _run_full_debug(
    settings: Settings,
    output: Path | None,
    debug_tracer: DebugTracer,
) -> int:
    model = _require_model(settings)
    started_at = datetime.now(UTC)
    sensitive_values = (settings.api_key.get_secret_value(),)
    debug_tracer.emit(
        "model.resolve",
        source="settings",
        model=redact_text(model, sensitive_values),
    )
    async with _make_client_with_debug(settings, debug_tracer) as client:
        style = await client.ensure_style()
        _print_run_header(len(CHECK_ORDER), style)
        ctx = RunContext(model=model, latency_rounds=settings.latency_rounds)
        results = await _run_named_checks(client, ctx, CHECK_ORDER, sensitive_values)
        style = client.style
    code = _finalize(settings, results, started_at, output, style)
    _print_summary(results, model, style, sensitive_values)
    return code


async def _run_single(settings: Settings, check_name: str, output: Path | None) -> int:
    if check_name != "models_list":
        _require_model(settings)
    model = settings.model or "(unspecified)"
    started_at = datetime.now(UTC)
    async with _make_client(settings) as client:
        await client.ensure_style()
        ctx = RunContext(model=model, latency_rounds=settings.latency_rounds)
        result = await CHECK_REGISTRY[check_name](client, ctx)
        style = client.style
    _print_result(result, (settings.api_key.get_secret_value(),))
    return _finalize(settings, [result], started_at, output, style)


async def _run_single_debug(
    settings: Settings,
    check_name: str,
    output: Path | None,
    debug_tracer: DebugTracer,
) -> int:
    if check_name != "models_list":
        model = _require_model(settings)
        model_source = "settings"
    else:
        model = settings.model or "(unspecified)"
        model_source = "not_required" if settings.model is None else "settings"
    sensitive_values = (settings.api_key.get_secret_value(),)
    debug_tracer.emit(
        "model.resolve",
        check=check_name,
        source=model_source,
        model=redact_text(model, sensitive_values),
    )
    started_at = datetime.now(UTC)
    async with _make_client_with_debug(settings, debug_tracer) as client:
        await client.ensure_style()
        ctx = RunContext(model=model, latency_rounds=settings.latency_rounds)
        result = await CHECK_REGISTRY[check_name](client, ctx)
        style = client.style
    _print_result(result, sensitive_values)
    return _finalize(settings, [result], started_at, output, style)


def _select_model_interactive(
    models: list[str],
    sensitive_values: tuple[str, ...] = (),
) -> str:
    if not models:
        _print_notice("/v1/models returned no model IDs. Enter a model name manually.")
        return _prompt_with_navigation("Model name")

    table = Table(
        title="Model catalog",
        box=box.SIMPLE_HEAVY,
        border_style="cyan",
        show_lines=False,
        expand=False,
    )
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("Model ID", overflow="fold", style="white")
    for index, model in enumerate(models, start=1):
        table.add_row(str(index), redact_text(model, sensitive_values))
    stderr_console.print(table)

    while True:
        raw = cast(
            str,
            click.prompt(
                f"Choose a model [1-{len(models)}] or type a custom model id ({NAVIGATION_HINT})",
                type=str,
                default="",
                show_default=False,
            ),
        ).strip()
        action = _navigation_action(raw)
        if action is not None:
            raise NavigationExit(action)
        if raw.isdigit():
            selected_index = int(raw)
            if 1 <= selected_index <= len(models):
                return models[selected_index - 1]
        elif raw:
            return raw
        _print_notice("Enter a valid model number or model id.")


def _print_summary(
    results: list[TestResultUnion],
    model: str,
    style: ApiStyle,
    sensitive_values: tuple[str, ...] = (),
) -> None:
    counts = {status: 0 for status in CheckStatus}
    for result in results:
        counts[result.status] += 1
    if _plain_console():
        stderr_console.print(
            "summary | "
            f"model={redact_text(model, sensitive_values)} | provider={style.value} | "
            f"passed={counts[CheckStatus.PASSED]} | "
            f"warning={counts[CheckStatus.WARNING]} | "
            f"failed={counts[CheckStatus.FAILED]} | "
            f"error={counts[CheckStatus.ERROR]} | "
            f"skipped={counts[CheckStatus.SKIPPED]}"
        )
        return

    table = Table(
        title="Run summary",
        box=box.SIMPLE_HEAVY,
        border_style="cyan",
        show_header=True,
        expand=False,
    )
    table.add_column("Target", style="dim")
    table.add_column("Value", style="white", overflow="fold")
    table.add_row("model", redact_text(model, sensitive_values))
    table.add_row("provider", style.value)
    table.add_row("passed", str(counts[CheckStatus.PASSED]), style="green")
    table.add_row("warning", str(counts[CheckStatus.WARNING]), style="yellow")
    table.add_row("failed", str(counts[CheckStatus.FAILED]), style="red")
    table.add_row("error", str(counts[CheckStatus.ERROR]), style="bold red")
    if counts[CheckStatus.SKIPPED]:
        table.add_row("skipped", str(counts[CheckStatus.SKIPPED]), style="dim")
    stderr_console.print(table)


async def _run_interactive(
    api_style: str,
    timeout: int | None,
    latency_rounds: int | None,
    output: Path,
    debug_tracer: DebugTracer | None = None,
) -> int:
    debug = debug_tracer or make_debug_tracer(False)
    api_key = ""
    base_url = _prompt_with_navigation("Endpoint URL")
    api_key = _prompt_with_navigation("API key", hide_input=True)
    add_sensitive_value(api_key)
    bootstrap_settings = _settings_from_options(
        base_url=base_url,
        api_key=api_key,
        model=None,
        api_style=api_style,
        timeout=timeout,
        latency_rounds=latency_rounds,
    )

    started_at = datetime.now(UTC)

    try:
        debug.emit(
            "interactive.input",
            base_url=_redacted_endpoint(base_url, (api_key,)),
            api_style=api_style,
        )
        async with _make_client_with_debug(bootstrap_settings, debug) as client:
            style = await client.ensure_style()
            _print_key_value("detected_provider", style.value, PROVIDER_STYLES[style.value])

            models_result = cast(
                ModelsListResult,
                await CHECK_REGISTRY["models_list"](
                    client,
                    RunContext(
                        model="(unused)",
                        latency_rounds=bootstrap_settings.latency_rounds,
                    ),
                ),
            )
            if models_result.models:
                _print_key_value("models_discovered", str(len(models_result.models)), "green")
            elif models_result.status in {CheckStatus.FAILED, CheckStatus.ERROR}:
                _print_notice(
                    "Model enumeration failed; you can still enter a model manually."
                )

            model = _select_model_interactive(models_result.models, (api_key,))
            debug.emit(
                "model.resolve",
                source="interactive_selection",
                model=redact_text(model, (api_key,)),
                catalog_count=len(models_result.models),
            )
            _print_key_value(
                "selected_model",
                redact_text(model, (api_key,)),
                "green",
            )

            run_settings = _settings_from_options(
                base_url=base_url,
                api_key=api_key,
                model=model,
                api_style=style.value,
                timeout=timeout,
                latency_rounds=latency_rounds,
            )
            ctx = RunContext(model=model, latency_rounds=run_settings.latency_rounds)
            results: list[TestResultUnion] = [models_result]
            _print_run_header(len(CHECK_ORDER) - 1, style)
            results.extend(await _run_named_checks(client, ctx, CHECK_ORDER[1:], (api_key,)))
    except NavigationExit:
        raise
    except Exception as exc:
        logger.exception("interactive.failed")
        error = redact_text(f"{type(exc).__name__}: {exc}", (api_key,))
        if _plain_console():
            stderr_console.print(f"error={error}")
        else:
            stderr_console.print(
                Panel(
                    Text(error, "bold red"),
                    title="[bold red]error[/]",
                    border_style="red",
                    box=box.ROUNDED,
                )
            )
        return 1

    code = _finalize(run_settings, results, started_at, output, style)
    _print_summary(results, model, style, (api_key,))
    return code


def _common_options(fn: Callable[..., Any]) -> Callable[..., Any]:
    decorators = [
        click.option("--base-url", default=None, help="Proxy base URL (overrides env)."),
        click.option("--api-key", default=None, help="API key (overrides env)."),
        click.option("--model", default=None, help="Model name (overrides env)."),
        click.option(
            "--api-style",
            type=click.Choice(API_STYLE_CHOICES),
            default=None,
            help="API style: auto (default), openai, anthropic.",
        ),
        click.option(
            "--timeout", type=int, default=None, help="Per-request read timeout in seconds."
        ),
        click.option("--latency-rounds", type=int, default=None, help="Rounds for latency probe."),
        click.option(
            "--output",
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            help="Write JSON report to PATH (single-check commands too).",
        ),
        click.option(
            "--log-file",
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            help="Write structured JSON logs to PATH.",
        ),
        click.option(
            "--capture",
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            help="Write sanitized forensic capture to PATH.",
        ),
        click.option(
            "--artifacts-dir",
            type=click.Path(file_okay=False, path_type=Path),
            default=None,
            help="Directory for default reports, logs, and captures.",
        ),
        click.option("--debug/--no-debug", default=False, help="Print request trace events."),
        click.option("--trace", "debug", flag_value=True, help="Alias for --debug."),
        click.option(
            "--debug-format",
            type=click.Choice(DEBUG_FORMAT_CHOICES),
            default="human",
            help="Debug trace format: human or json.",
        ),
        click.option("-v", "--verbose", is_flag=True, help="Enable DEBUG-level logs."),
    ]
    for dec in reversed(decorators):
        fn = dec(fn)
    return fn


def _artifact_path(
    artifacts_dir: Path | None,
    subdir: str,
    filename: str,
) -> Path:
    base = artifacts_dir or CAPTURES_DIR.parent
    return base / subdir / filename


def _default_report_path_for(artifacts_dir: Path | None) -> Path:
    if artifacts_dir is None:
        return default_report_path()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _artifact_path(artifacts_dir, "reports", f"report-{stamp}.json")


def _default_log_path_for(artifacts_dir: Path | None) -> Path:
    if artifacts_dir is None:
        return default_log_path()
    return _artifact_path(artifacts_dir, "logs", "forensics.log")


def _effective_capture_path(capture: Path | None, artifacts_dir: Path | None) -> Path | None:
    if capture is not None:
        return capture
    if artifacts_dir is None:
        return None
    return _artifact_path(artifacts_dir, "captures", DEFAULT_CAPTURE_NAME)


def _effective_single_output_path(
    output: Path | None,
    artifacts_dir: Path | None,
    check_name: str,
) -> Path | None:
    if output is not None:
        return output
    if artifacts_dir is None:
        return None
    return _artifact_path(artifacts_dir, "reports", f"{check_name}.json")


def _execute_async(coro: Coroutine[Any, Any, int]) -> int:
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        stderr_console.print("[yellow]Interrupted[/]")
        return 130


async def _run_interactive_entry_async(
    api_style: str,
    timeout: int | None,
    latency_rounds: int | None,
    output_path: Path,
    debug_tracer: DebugTracer,
) -> int:
    return await _run_interactive(api_style, timeout, latency_rounds, output_path, debug_tracer)


def _interactive_entry(
    *,
    api_style: str,
    timeout: int | None,
    latency_rounds: int | None,
    output: Path | None,
    log_file: Path | None,
    capture: Path | None,
    artifacts_dir: Path | None,
    debug: bool,
    debug_format: str,
    verbose: bool,
    pause: bool,
    back_code: int = 0,
) -> int:
    output_path = output or _default_report_path_for(artifacts_dir)
    effective_log_file = log_file or _default_log_path_for(artifacts_dir)
    effective_capture = _effective_capture_path(capture, artifacts_dir)
    configure(verbose=verbose, log_file=effective_log_file)
    debug_tracer, capture_tracer = _make_trace_bundle(
        debug=debug,
        debug_format=debug_format,
        capture=effective_capture,
        command="interactive",
        sensitive_values=(),
    )
    preview_settings = _settings_from_options(
        base_url="(prompt)",
        api_key="(prompt)",
        model=None,
        api_style=api_style,
        timeout=timeout,
        latency_rounds=latency_rounds,
    )
    _print_banner(
        mode="interactive",
        settings=preview_settings,
        output=output_path,
        log_file=effective_log_file,
        sensitive_values=(),
    )
    try:
        return _execute_async(
            _run_interactive_entry_async(
                api_style,
                timeout,
                latency_rounds,
                output_path,
                debug_tracer,
            )
        )
    except NavigationExit as exc:
        if exc.action == "quit":
            return 0
        return back_code
    finally:
        _write_capture_if_requested(effective_capture, capture_tracer)
        if pause:
            click.pause("Press any key to close...")


def _run_configured_entry() -> int:
    settings = _settings_from_options(
        base_url=None,
        api_key=None,
        model=None,
        api_style=None,
        timeout=None,
        latency_rounds=None,
    )
    _require_model(settings)
    output_path = _default_report_path_for(None)
    log_file = _default_log_path_for(None)
    sensitive_values = (settings.api_key.get_secret_value(),)
    configure(verbose=False, log_file=log_file, sensitive_values=sensitive_values)
    debug_tracer = make_debug_tracer(False)
    _print_banner(
        mode="run",
        settings=settings,
        output=output_path,
        log_file=log_file,
        sensitive_values=sensitive_values,
    )
    return _execute_async(_run_full_debug(settings, output_path, debug_tracer))


def _models_entry() -> int:
    settings = _settings_from_options(
        base_url=None,
        api_key=None,
        model=None,
        api_style=None,
        timeout=None,
        latency_rounds=None,
    )
    sensitive_values = (settings.api_key.get_secret_value(),)
    configure(verbose=False, log_file=None, sensitive_values=sensitive_values)
    debug_tracer = make_debug_tracer(False)
    return _execute_async(_run_single_debug(settings, "models_list", None, debug_tracer))


def _render_replay_file(capture_file: Path) -> int:
    try:
        capture = read_capture(capture_file)
    except CaptureError as exc:
        raise click.ClickException(str(exc)) from exc
    for line in render_capture_human(capture):
        click.echo(line)
    return 0


def _replay_menu() -> str:
    stderr_console.print("Replay capture file. Enter a path, or 'b' to go back, 'q' to quit.")
    while True:
        raw = cast(str, click.prompt("Capture file", default="", show_default=False)).strip()
        lowered = raw.lower()
        if not raw or lowered in BACK_CHOICES:
            return "back"
        if lowered in QUIT_CHOICES:
            return "quit"

        capture_file = Path(raw).expanduser()
        if not capture_file.exists():
            _print_notice(f"File does not exist: {capture_file}", CheckStatus.WARNING)
            continue
        if capture_file.is_dir():
            _print_notice(f"Expected a capture file, got directory: {capture_file}")
            continue
        try:
            _render_replay_file(capture_file)
        except click.ClickException as exc:
            _print_notice(exc.message, CheckStatus.WARNING)
            continue
        return "done"


def _print_main_menu() -> None:
    if _plain_console():
        stderr_console.print("aipf | main menu")
        stderr_console.print("1  Guided audit (recommended)")
        stderr_console.print("2  Run full audit from env/.env")
        stderr_console.print("3  List models from env/.env")
        stderr_console.print("4  Replay capture file")
        stderr_console.print("5  Show help")
        stderr_console.print("0  Quit")
        return

    table = Table(
        title="Main menu",
        box=box.SIMPLE_HEAVY,
        border_style="cyan",
        show_header=False,
        expand=False,
    )
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Action", style="white")
    table.add_row("1", "Guided audit (recommended)")
    table.add_row("2", "Run full audit from env/.env")
    table.add_row("3", "List models from env/.env")
    table.add_row("4", "Replay capture file")
    table.add_row("5", "Show help")
    table.add_row("0", "Quit")
    stderr_console.print(
        Panel(
            table,
            title="[bold cyan]aipf[/]",
            subtitle="[dim]choose a workflow[/]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )


def _run_guided_from_menu() -> int:
    return _interactive_entry(
        api_style="auto",
        timeout=None,
        latency_rounds=None,
        output=None,
        log_file=None,
        capture=None,
        artifacts_dir=None,
        debug=False,
        debug_format="human",
        verbose=False,
        pause=False,
        back_code=MENU_BACK_CODE,
    )


def _prompt_start_guided_after_config_error() -> str:
    _print_notice("Enter 'y' to start guided audit, 'b' to go back, or 'q' to quit.")
    while True:
        raw = cast(
            str,
            click.prompt(
                "Start guided audit? [Y/n/b/q]",
                default="y",
                show_default=False,
            ),
        ).strip()
        action_choice = _navigation_action(raw)
        if action_choice is not None:
            return action_choice
        if raw.lower() in {"", "y", "yes"}:
            return "yes"
        if raw.lower() in {"n", "no"}:
            return "no"
        _print_notice("Enter y, n, b, or q.")


def _run_menu_action_with_config_fallback(action: Callable[[], int]) -> int:
    try:
        return action()
    except click.UsageError as exc:
        _print_notice(str(exc), CheckStatus.WARNING)
    decision = _prompt_start_guided_after_config_error()
    if decision == "quit":
        return 0
    if decision != "yes":
        return MENU_BACK_CODE
    try:
        return _run_guided_from_menu()
    except NavigationExit as nav:
        if nav.action == "quit":
            return 0
        return MENU_BACK_CODE


def _open_main_menu(ctx: click.Context) -> None:
    while True:
        _print_main_menu()
        choice = cast(
            str,
            click.prompt(
                "Select",
                type=click.Choice(MAIN_MENU_CHOICES, case_sensitive=False),
                default="1",
                show_choices=False,
            ),
        ).lower()
        if choice == "1":
            try:
                result = _run_guided_from_menu()
            except NavigationExit as exc:
                if exc.action == "quit":
                    ctx.exit(0)
                continue
            if result == 2:
                continue
            ctx.exit(result)
        if choice == "2":
            result = _run_menu_action_with_config_fallback(_run_configured_entry)
            if result == MENU_BACK_CODE:
                continue
            ctx.exit(result)
        if choice == "3":
            result = _run_menu_action_with_config_fallback(_models_entry)
            if result == MENU_BACK_CODE:
                continue
            ctx.exit(result)
        if choice == "4":
            replay_result = _replay_menu()
            if replay_result == "quit":
                ctx.exit(0)
            continue
        if choice == "5":
            click.echo(ctx.get_help())
            continue
        ctx.exit(0)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """aipf — API Proxy Forensics Toolkit."""
    if ctx.invoked_subcommand is not None:
        return
    if not _stdin_is_interactive():
        click.echo(ctx.get_help())
        return
    _open_main_menu(ctx)


def _wrap_single_check(check_name: str) -> Callable[..., None]:
    @_common_options
    def _impl(
        base_url: str | None,
        api_key: str | None,
        model: str | None,
        api_style: str | None,
        timeout: int | None,
        latency_rounds: int | None,
        output: Path | None,
        log_file: Path | None,
        capture: Path | None,
        artifacts_dir: Path | None,
        debug: bool,
        debug_format: str,
        verbose: bool,
    ) -> None:
        settings = _settings_from_options(
            base_url, api_key, model, api_style, timeout, latency_rounds
        )
        effective_capture = _effective_capture_path(capture, artifacts_dir)
        output_path = _effective_single_output_path(output, artifacts_dir, check_name)
        configure(
            verbose=verbose,
            log_file=log_file,
            sensitive_values=(settings.api_key.get_secret_value(),),
        )
        debug_tracer, capture_tracer = _make_trace_bundle(
            debug=debug,
            debug_format=debug_format,
            capture=effective_capture,
            command=check_name,
            sensitive_values=(settings.api_key.get_secret_value(),),
        )
        try:
            code = _execute_async(
                _run_single_debug(settings, check_name, output_path, debug_tracer)
            )
        finally:
            _write_capture_if_requested(effective_capture, capture_tracer)
        sys.exit(code)

    return _impl


@cli.command(name="run")
@_common_options
def run_cmd(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    api_style: str | None,
    timeout: int | None,
    latency_rounds: int | None,
    output: Path | None,
    log_file: Path | None,
    capture: Path | None,
    artifacts_dir: Path | None,
    debug: bool,
    debug_format: str,
    verbose: bool,
) -> None:
    """Execute all 8 forensics checks and write a full JSON report."""
    settings = _settings_from_options(
        base_url, api_key, model, api_style, timeout, latency_rounds
    )
    output_path = output or _default_report_path_for(artifacts_dir)
    effective_log_file = log_file or _default_log_path_for(artifacts_dir)
    effective_capture = _effective_capture_path(capture, artifacts_dir)
    configure(
        verbose=verbose,
        log_file=effective_log_file,
        sensitive_values=(settings.api_key.get_secret_value(),),
    )
    debug_tracer, capture_tracer = _make_trace_bundle(
        debug=debug,
        debug_format=debug_format,
        capture=effective_capture,
        command="run",
        sensitive_values=(settings.api_key.get_secret_value(),),
    )
    _print_banner(
        mode="run",
        settings=settings,
        output=output_path,
        log_file=effective_log_file,
        sensitive_values=(settings.api_key.get_secret_value(),),
    )
    try:
        code = _execute_async(_run_full_debug(settings, output_path, debug_tracer))
    finally:
        _write_capture_if_requested(effective_capture, capture_tracer)
    sys.exit(code)


@cli.command(name="interactive")
@click.option(
    "--api-style",
    type=click.Choice(API_STYLE_CHOICES),
    default="auto",
    help="Override provider style. Usually leave as auto.",
)
@click.option(
    "--timeout", type=int, default=None, help="Per-request read timeout in seconds."
)
@click.option("--latency-rounds", type=int, default=None, help="Rounds for latency probe.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write JSON report to PATH. Defaults to aipf-artifacts/reports/report-<timestamp>.json.",
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write structured JSON logs to PATH.",
)
@click.option(
    "--capture",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write sanitized forensic capture to PATH.",
)
@click.option(
    "--artifacts-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for default report, log, and capture outputs.",
)
@click.option("--debug/--no-debug", default=False, help="Print request trace events.")
@click.option("--trace", "debug", flag_value=True, help="Alias for --debug.")
@click.option(
    "--debug-format",
    type=click.Choice(DEBUG_FORMAT_CHOICES),
    default="human",
    help="Debug trace format: human or json.",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable DEBUG-level logs.")
@click.option("--pause/--no-pause", default=False, help="Pause before closing the window.")
def interactive_cmd(
    api_style: str,
    timeout: int | None,
    latency_rounds: int | None,
    output: Path | None,
    log_file: Path | None,
    capture: Path | None,
    artifacts_dir: Path | None,
    debug: bool,
    debug_format: str,
    verbose: bool,
    pause: bool,
) -> None:
    """Prompt for endpoint and API key, then run the full probe interactively."""
    code = _interactive_entry(
        api_style=api_style,
        timeout=timeout,
        latency_rounds=latency_rounds,
        output=output,
        log_file=log_file,
        capture=capture,
        artifacts_dir=artifacts_dir,
        debug=debug,
        debug_format=debug_format,
        verbose=verbose,
        pause=pause,
    )
    sys.exit(code)


@cli.command(name="replay")
@click.argument("capture_file", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(REPLAY_FORMAT_CHOICES),
    default="human",
    help="Replay output format: human or json.",
)
def replay_cmd(capture_file: Path, output_format: str) -> None:
    """Replay a sanitized capture file without making HTTP requests."""
    if output_format == "json":
        try:
            capture = read_capture(capture_file)
        except CaptureError as exc:
            raise click.ClickException(str(exc)) from exc
        for line in render_capture_json_lines(capture):
            click.echo(line)
        return

    _render_replay_file(capture_file)


cli.command(name="models")(_wrap_single_check("models_list"))
cli.command(name="completion")(_wrap_single_check("completion"))
cli.command(name="stream")(_wrap_single_check("streaming"))
cli.command(name="inject")(_wrap_single_check("injection"))
cli.command(name="leaks")(_wrap_single_check("leaks"))
cli.command(name="fingerprint")(_wrap_single_check("fingerprint"))
cli.command(name="tool-ids")(_wrap_single_check("tool_ids"))
cli.command(name="latency")(_wrap_single_check("latency"))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
