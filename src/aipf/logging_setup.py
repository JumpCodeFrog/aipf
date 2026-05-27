from __future__ import annotations

import logging
from pathlib import Path

from pythonjsonlogger.json import JsonFormatter
from rich.logging import RichHandler

from aipf.redaction import REDACTED, is_sensitive_key, redact_data, redact_text

_LOG_RECORD_RESERVED = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}

_SENSITIVE_VALUES: list[str] = []


def add_sensitive_value(value: str | None) -> None:
    if value is None or len(value) < 8 or value in _SENSITIVE_VALUES:
        return
    _SENSITIVE_VALUES.append(value)


def _set_sensitive_values(values: tuple[str, ...]) -> None:
    _SENSITIVE_VALUES.clear()
    for value in values:
        add_sensitive_value(value)


def _sensitive_values() -> tuple[str, ...]:
    return tuple(_SENSITIVE_VALUES)


class RedactFilter(logging.Filter):
    """Replace sensitive values in log record extras and message bodies."""

    def filter(self, record: logging.LogRecord) -> bool:
        sensitive_values = _sensitive_values()
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg, sensitive_values)
        if record.args:
            record.args = redact_data(record.args, sensitive_values)
        for key in list(record.__dict__.keys()):
            if key in _LOG_RECORD_RESERVED:
                continue
            record.__dict__[key] = (
                REDACTED
                if is_sensitive_key(key)
                else redact_data(record.__dict__[key], sensitive_values)
            )
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text, sensitive_values)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info, sensitive_values)
        return True


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), _sensitive_values())


class RedactingJsonFormatter(JsonFormatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), _sensitive_values())


def configure(
    verbose: bool = False,
    log_file: Path | None = None,
    sensitive_values: tuple[str, ...] = (),
) -> None:
    root_level = logging.DEBUG if verbose else logging.INFO
    console_level = logging.DEBUG if verbose else logging.WARNING

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(root_level)
    _set_sensitive_values(sensitive_values)

    redact = RedactFilter()

    rich_handler = RichHandler(
        rich_tracebacks=False,
        show_path=False,
        markup=False,
        log_time_format="%H:%M:%S",
    )
    rich_handler.setLevel(console_level)
    rich_handler.addFilter(redact)
    rich_handler.setFormatter(RedactingFormatter("%(message)s"))
    root.addHandler(rich_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(root_level)
        file_handler.addFilter(redact)
        file_handler.setFormatter(
            RedactingJsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            )
        )
        root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
