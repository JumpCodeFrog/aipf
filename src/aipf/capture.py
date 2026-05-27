from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aipf import __version__
from aipf.debug_trace import _format_human
from aipf.redaction import redact_data

CAPTURE_SCHEMA_VERSION = 1
MAX_CAPTURE_EVENTS = 20_000
MAX_CAPTURE_BYTES = 5_000_000
MAX_FIELD_STRING_CHARS = 500
CAPTURE_TRUNCATED_EVENT = "capture.truncated"


class CaptureError(RuntimeError):
    pass


class CaptureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    t_ms: float
    event: str
    fields: dict[str, Any] = Field(default_factory=dict)


class CaptureMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "aipf"
    tool_version: str
    python_version: str
    started_at: datetime
    finished_at: datetime | None = None
    command: str
    event_count: int = 0
    truncated: bool = False
    max_events: int = MAX_CAPTURE_EVENTS
    max_bytes: int = MAX_CAPTURE_BYTES
    notes: list[str] = Field(default_factory=list)


class CaptureFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    meta: CaptureMeta
    events: list[CaptureEvent] = Field(default_factory=list)


class CaptureTracer:
    enabled = True

    def __init__(
        self,
        *,
        command: str,
        sensitive_values: tuple[str, ...] = (),
        max_events: int = MAX_CAPTURE_EVENTS,
        max_bytes: int = MAX_CAPTURE_BYTES,
    ) -> None:
        self._sensitive_values = sensitive_values
        self._started_perf = time.perf_counter()
        self._events: list[CaptureEvent] = []
        self._truncated = False
        self._max_events = max_events
        self._max_bytes = max_bytes
        self._meta = CaptureMeta(
            tool_version=__version__,
            python_version=".".join(str(v) for v in sys.version_info[:3]),
            started_at=datetime.now(UTC),
            command=command,
            max_events=max_events,
            max_bytes=max_bytes,
        )

    def emit(self, event: str, **fields: object) -> None:
        if self._truncated:
            return
        sanitized_fields = cast(
            dict[str, Any],
            _sanitize_capture_value(redact_data(fields, self._sensitive_values)),
        )
        candidate = CaptureEvent(
            seq=len(self._events) + 1,
            t_ms=round((time.perf_counter() - self._started_perf) * 1000, 2),
            event=event,
            fields=sanitized_fields,
        )
        if len(self._events) >= self._max_events:
            self._append_truncated("max_events")
            return
        self._events.append(candidate)
        if self._estimated_size() > self._max_bytes:
            self._events.pop()
            self._append_truncated("max_bytes")

    def build(self) -> CaptureFile:
        meta = self._meta.model_copy(
            update={
                "finished_at": datetime.now(UTC),
                "event_count": len(self._events),
                "truncated": self._truncated,
            }
        )
        return CaptureFile(meta=meta, events=list(self._events))

    def write(self, path: Path) -> CaptureFile:
        capture = self.build()
        write_capture(path, capture)
        return capture

    def _append_truncated(self, reason: str) -> None:
        self._truncated = True
        self._meta.notes.append(f"capture truncated: {reason}")
        self._events.append(
            CaptureEvent(
                seq=len(self._events) + 1,
                t_ms=round((time.perf_counter() - self._started_perf) * 1000, 2),
                event=CAPTURE_TRUNCATED_EVENT,
                fields={"reason": reason},
            )
        )

    def _estimated_size(self) -> int:
        payload = CaptureFile(
            meta=self._meta.model_copy(
                update={"event_count": len(self._events), "truncated": self._truncated}
            ),
            events=self._events,
        ).model_dump(mode="json")
        return len(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def write_capture(path: Path, capture: CaptureFile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = capture.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def read_capture(path: Path) -> CaptureFile:
    try:
        raw = path.read_text("utf-8")
    except OSError as exc:
        raise CaptureError(f"Unable to read capture: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"Invalid capture JSON: {exc}") from exc
    try:
        return CaptureFile.model_validate(payload)
    except ValidationError as exc:
        raise CaptureError(f"Invalid capture schema: {exc}") from exc


def render_capture_human(capture: CaptureFile) -> list[str]:
    lines = [
        (
            f"capture schema=v{capture.schema_version} command={capture.meta.command} "
            f"events={capture.meta.event_count} truncated={str(capture.meta.truncated).lower()}"
        )
    ]
    for event in capture.events:
        payload = {"event": event.event, "t_ms": event.t_ms, **event.fields}
        lines.append(f"{event.seq:04d} {_format_human(payload)}")
    return lines


def render_capture_json_lines(capture: CaptureFile) -> list[str]:
    header = {
        "type": "capture.meta",
        "schema_version": capture.schema_version,
        **capture.meta.model_dump(mode="json"),
    }
    lines = [json.dumps(header, sort_keys=True, ensure_ascii=False)]
    for event in capture.events:
        payload = {
            "type": "capture.event",
            "schema_version": capture.schema_version,
            "seq": event.seq,
            "t_ms": event.t_ms,
            "event": event.event,
            **event.fields,
        }
        lines.append(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return lines


def _sanitize_capture_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_capture_string(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        return _sanitize_capture_sequence(value)
    if isinstance(value, dict):
        return _sanitize_capture_mapping(value)
    return repr(value)[:MAX_FIELD_STRING_CHARS]


def _sanitize_capture_string(value: str) -> str:
    if len(value) > MAX_FIELD_STRING_CHARS:
        return value[:MAX_FIELD_STRING_CHARS] + "...[truncated]"
    return value


def _sanitize_capture_sequence(value: Sequence[Any]) -> list[Any]:
    return [_sanitize_capture_value(item) for item in value[:50]]


def _sanitize_capture_mapping(value: dict[Any, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for index, key in enumerate(sorted(value.keys(), key=str)):
        if index >= 100:
            sanitized["...[truncated]"] = True
            break
        safe_key = str(key)
        sanitized[safe_key] = _sanitize_capture_value(value[key])
    return sanitized
