from __future__ import annotations

import json
import sys
import time
from typing import Any, Literal, Protocol, TextIO, cast

from aipf.redaction import redact_data

DebugFormat = Literal["human", "json"]


class DebugTracer(Protocol):
    enabled: bool

    def emit(self, event: str, **fields: object) -> None:
        """Emit a redacted debug event."""


class NullDebugTracer:
    enabled = False

    def emit(self, event: str, **fields: object) -> None:
        return None


class ConsoleDebugTracer:
    enabled = True

    def __init__(
        self,
        *,
        output_format: DebugFormat = "human",
        sensitive_values: tuple[str, ...] = (),
        stream: TextIO | None = None,
    ) -> None:
        self._format = output_format
        self._sensitive_values = sensitive_values
        self._stream = stream or sys.stderr
        self._started_at = time.perf_counter()

    def emit(self, event: str, **fields: object) -> None:
        payload: dict[str, object] = {
            "event": event,
            "t_ms": round((time.perf_counter() - self._started_at) * 1000, 2),
            **fields,
        }
        redacted = cast(dict[str, Any], redact_data(payload, self._sensitive_values))
        if self._format == "json":
            self._stream.write(json.dumps(redacted, sort_keys=True, ensure_ascii=False))
            self._stream.write("\n")
            self._stream.flush()
            return
        self._stream.write(_format_human(redacted))
        self._stream.write("\n")
        self._stream.flush()


def make_debug_tracer(
    enabled: bool,
    *,
    output_format: DebugFormat = "human",
    sensitive_values: tuple[str, ...] = (),
) -> DebugTracer:
    if not enabled:
        return NullDebugTracer()
    return ConsoleDebugTracer(
        output_format=output_format,
        sensitive_values=sensitive_values,
    )


class TeeDebugTracer:
    @property
    def enabled(self) -> bool:
        return any(tracer.enabled for tracer in self._tracers)

    def __init__(self, *tracers: DebugTracer) -> None:
        self._tracers = tuple(tracers)

    def emit(self, event: str, **fields: object) -> None:
        for tracer in self._tracers:
            tracer.emit(event, **fields)


def _format_human(payload: dict[str, Any]) -> str:
    event = str(payload.get("event", "debug"))
    t_ms = payload.get("t_ms")
    prefix = f"trace +{t_ms}ms {event}"
    fields = [
        f"{key}={_format_human_value(value)}"
        for key, value in payload.items()
        if key not in {"event", "t_ms"} and value is not None
    ]
    if not fields:
        return prefix
    return f"{prefix} {' '.join(fields)}"


def _format_human_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        if not value:
            return '""'
        if any(char.isspace() for char in value):
            return json.dumps(value, ensure_ascii=False)
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
