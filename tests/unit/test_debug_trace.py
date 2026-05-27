from __future__ import annotations

import io
import json

from aipf.debug_trace import ConsoleDebugTracer


def test_json_debug_trace_redacts_sensitive_values() -> None:
    stream = io.StringIO()
    tracer = ConsoleDebugTracer(
        output_format="json",
        sensitive_values=("sk-test-secret-value",),
        stream=stream,
    )

    tracer.emit(
        "http.request.start",
        url="https://example.test/v1/models?api_key=sk-test-secret-value",
        authorization="Bearer sk-test-secret-value",
    )

    raw = stream.getvalue()
    payload = json.loads(raw)

    assert "sk-test-secret-value" not in raw
    assert payload["event"] == "http.request.start"
    assert payload["url"].endswith("api_key=***")
    assert payload["authorization"] == "***"


def test_human_debug_trace_is_readable() -> None:
    stream = io.StringIO()
    tracer = ConsoleDebugTracer(output_format="human", stream=stream)

    tracer.emit("http.retry", next_attempt=2, sleep_s=0.25, reason="http_429")

    line = stream.getvalue()
    assert line.startswith("trace +")
    assert "http.retry" in line
    assert "next_attempt=2" in line
    assert "sleep_s=0.25" in line
