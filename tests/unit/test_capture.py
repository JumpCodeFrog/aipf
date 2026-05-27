from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipf.capture import (
    CAPTURE_TRUNCATED_EVENT,
    CaptureError,
    CaptureTracer,
    read_capture,
    render_capture_human,
    render_capture_json_lines,
)


def test_capture_tracer_writes_deterministic_redacted_schema(tmp_path: Path) -> None:
    path = tmp_path / "capture.json"
    secret = "sk-test-secret-value"
    tracer = CaptureTracer(command="completion", sensitive_values=(secret,))

    tracer.emit(
        "http.request.start",
        url=f"https://example.test/v1/messages?api_key={secret}",
        prompt="do not store raw prompt here",
        nested={"authorization": f"Bearer {secret}"},
    )
    capture = tracer.write(path)

    raw = path.read_text("utf-8")
    payload = json.loads(raw)
    loaded = read_capture(path)

    assert secret not in raw
    assert payload["schema_version"] == 1
    assert payload["meta"]["command"] == "completion"
    assert payload["meta"]["event_count"] == 1
    assert capture.events[0].seq == 1
    assert loaded.events[0].fields["url"].endswith("api_key=***")
    assert loaded.events[0].fields["nested"]["authorization"] == "***"
    assert raw == path.read_text("utf-8")


def test_capture_tracer_bounds_event_count() -> None:
    tracer = CaptureTracer(command="run", max_events=1)

    tracer.emit("first")
    tracer.emit("second")
    capture = tracer.build()

    assert capture.meta.truncated is True
    assert capture.meta.event_count == 2
    assert capture.events[-1].event == CAPTURE_TRUNCATED_EVENT
    assert capture.events[-1].fields["reason"] == "max_events"


def test_replay_renderers_include_timeline() -> None:
    tracer = CaptureTracer(command="stream")
    tracer.emit("http.retry", next_attempt=2, sleep_s=0.25)
    capture = tracer.build()

    human = "\n".join(render_capture_human(capture))
    json_lines = [json.loads(line) for line in render_capture_json_lines(capture)]

    assert "capture schema=v1 command=stream" in human
    assert "http.retry" in human
    assert json_lines[0]["type"] == "capture.meta"
    assert json_lines[1]["type"] == "capture.event"
    assert json_lines[1]["event"] == "http.retry"


def test_read_capture_rejects_invalid_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 999, "meta": {}, "events": []}\n', "utf-8")

    with pytest.raises(CaptureError):
        read_capture(path)
