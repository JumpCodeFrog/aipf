from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import respx
from click.testing import CliRunner

from aipf.cli import cli
from tests.conftest import BASE_URL


def _debug_json_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("event"), str):
            events.append(payload)
    return events


def test_aipf_run_writes_full_report(
    tmp_path: Path,
    sample_models_list_openai: dict[str, Any],
    sample_openai_chat_response: dict[str, Any],
    openai_stream_body: str,
) -> None:
    output = tmp_path / "report.json"
    log_file = tmp_path / "forensics.log"

    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=openai_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=sample_openai_chat_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        runner = CliRunner()
        res = runner.invoke(
            cli,
            [
                "run",
                "--base-url",
                BASE_URL,
                "--api-key",
                "k",
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--latency-rounds",
                "2",
                "--output",
                str(output),
                "--log-file",
                str(log_file),
            ],
            catch_exceptions=False,
        )

    # Exit code 0 (all passed) since responses don't trigger leaks/warnings.
    assert res.exit_code == 0, res.output
    assert "aipf | async LLM proxy audit | mode=run" in res.output
    assert "trace +" not in res.output
    assert "01/08 RUN MODELS" in res.output
    assert "01/08 [PASS] MODELS" in res.output
    assert "summary | model=gpt-test | provider=openai | passed=8" in res.output
    assert output.exists()
    payload = json.loads(output.read_text("utf-8"))
    assert payload["meta"]["api_style"] == "openai"
    kinds = [r["kind"] for r in payload["results"]]
    assert kinds == [
        "models_list",
        "completion",
        "streaming",
        "injection",
        "leaks",
        "fingerprint",
        "tool_ids",
        "latency",
    ]
    assert all(r["status"] == "passed" for r in payload["results"])


def test_aipf_run_uses_default_artifacts_dir(
    sample_models_list_openai: dict[str, Any],
    sample_openai_chat_response: dict[str, Any],
    openai_stream_body: str,
) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=openai_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=sample_openai_chat_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        with CliRunner().isolated_filesystem():
            res = CliRunner().invoke(
                cli,
                [
                    "run",
                    "--base-url",
                    BASE_URL,
                    "--api-key",
                    "k",
                    "--model",
                    "gpt-test",
                    "--api-style",
                    "openai",
                    "--latency-rounds",
                    "1",
                ],
                catch_exceptions=False,
            )
            reports = list(Path("aipf-artifacts/reports").glob("report-*.json"))
            assert res.exit_code == 0, res.output
            assert len(reports) == 1
            assert Path("aipf-artifacts/logs/forensics.log").exists()
            assert "report=aipf-artifacts/reports/report-" in res.output


def test_aipf_run_artifacts_dir_writes_default_capture(
    tmp_path: Path,
    sample_models_list_openai: dict[str, Any],
    sample_openai_chat_response: dict[str, Any],
    openai_stream_body: str,
) -> None:
    artifacts_dir = tmp_path / "audit-artifacts"
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=openai_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=sample_openai_chat_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        res = CliRunner().invoke(
            cli,
            [
                "run",
                "--base-url",
                BASE_URL,
                "--api-key",
                "k",
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--latency-rounds",
                "1",
                "--artifacts-dir",
                str(artifacts_dir),
            ],
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert len(list((artifacts_dir / "reports").glob("report-*.json"))) == 1
    assert (artifacts_dir / "logs" / "forensics.log").exists()
    assert (artifacts_dir / "captures" / "capture.json").exists()


def test_aipf_completion_debug_json_traces_http_and_model_flow(
    tmp_path: Path,
    sample_openai_chat_response: dict[str, Any],
) -> None:
    output = tmp_path / "completion.json"
    secret = "sk-test-secret-value"
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        route = router.post("/v1/chat/completions")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(
                200,
                json=sample_openai_chat_response,
                headers={"x-request-id": "req-test-1"},
            ),
        ]
        res = CliRunner().invoke(
            cli,
            [
                "completion",
                "--base-url",
                BASE_URL,
                "--api-key",
                secret,
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--debug",
                "--debug-format",
                "json",
                "--output",
                str(output),
            ],
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert secret not in res.output
    trace_events = _debug_json_events(res.output)
    event_names = {event["event"] for event in trace_events}
    assert "model.resolve" in event_names
    assert "http.request.start" in event_names
    assert "http.retry" in event_names
    assert "http.request.end" in event_names
    assert any(event.get("request_id") == "req-test-1" for event in trace_events)
    assert '"kind": "completion"' in res.output


def test_aipf_completion_capture_and_replay_json(
    tmp_path: Path,
    sample_openai_chat_response: dict[str, Any],
) -> None:
    output = tmp_path / "completion.json"
    capture = tmp_path / "capture.json"
    secret = "sk-test-secret-value"
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        route = router.post("/v1/chat/completions")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(
                200,
                json=sample_openai_chat_response,
                headers={"x-request-id": "req-capture-1"},
            ),
        ]
        res = CliRunner().invoke(
            cli,
            [
                "completion",
                "--base-url",
                BASE_URL,
                "--api-key",
                secret,
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--capture",
                str(capture),
                "--output",
                str(output),
            ],
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert "capture=" in res.output
    raw_capture = capture.read_text("utf-8")
    payload = json.loads(raw_capture)
    assert payload["schema_version"] == 1
    assert payload["meta"]["command"] == "completion"
    assert payload["meta"]["truncated"] is False
    assert secret not in raw_capture
    assert "prompt" not in raw_capture.lower()
    events = payload["events"]
    event_names = {event["event"] for event in events}
    assert "http.request.start" in event_names
    assert "http.retry" in event_names
    assert "chat.response.extract" in event_names
    assert any(event["fields"].get("request_id") == "req-capture-1" for event in events)

    replay = CliRunner().invoke(
        cli,
        ["replay", str(capture), "--format", "json"],
        catch_exceptions=False,
    )
    assert replay.exit_code == 0, replay.output
    replay_lines = [json.loads(line) for line in replay.output.splitlines()]
    assert replay_lines[0]["type"] == "capture.meta"
    assert any(line.get("event") == "http.retry" for line in replay_lines)
    assert secret not in replay.output


def test_aipf_replay_human_does_not_make_http_requests(
    tmp_path: Path,
) -> None:
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "meta": {
                    "tool": "aipf",
                    "tool_version": "0.1.0",
                    "python_version": "3.13.7",
                    "started_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:01Z",
                    "command": "completion",
                    "event_count": 1,
                    "truncated": False,
                    "max_events": 20000,
                    "max_bytes": 5000000,
                    "notes": [],
                },
                "events": [
                    {
                        "seq": 1,
                        "t_ms": 1.25,
                        "event": "http.request.end",
                        "fields": {"status": 200, "latency_ms": 12.3},
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        "utf-8",
    )

    with respx.mock(assert_all_called=False) as router:
        res = CliRunner().invoke(
            cli,
            ["replay", str(capture)],
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert router.calls.call_count == 0
    assert "capture schema=v1 command=completion" in res.output
    assert "http.request.end" in res.output


def test_aipf_stream_trace_alias_emits_stream_events(
    openai_stream_body: str,
) -> None:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=openai_stream_body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        )
        res = CliRunner().invoke(
            cli,
            [
                "stream",
                "--base-url",
                BASE_URL,
                "--api-key",
                "k",
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--trace",
            ],
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert "trace +" in res.output
    assert "stream.request.build" in res.output
    assert "stream.chunk" in res.output
    assert '"kind": "streaming"' in res.output


def test_aipf_single_command_writes_mini_report(
    tmp_path: Path,
    sample_models_list_openai: dict[str, Any],
) -> None:
    output = tmp_path / "models.json"
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )
        res = CliRunner().invoke(
            cli,
            [
                "models",
                "--base-url",
                BASE_URL,
                "--api-key",
                "k",
                "--api-style",
                "openai",
                "--output",
                str(output),
            ],
            catch_exceptions=False,
        )
    assert res.exit_code == 0, res.output
    assert "aipf | async LLM proxy audit" not in res.output
    assert '"kind": "models_list"' in res.output
    payload = json.loads(output.read_text("utf-8"))
    assert len(payload["results"]) == 1
    assert payload["results"][0]["kind"] == "models_list"
    assert payload["results"][0]["models"] == ["gpt-4o", "gpt-4o-mini"]


def test_aipf_interactive_flow(
    tmp_path: Path,
    sample_models_list_openai: dict[str, Any],
    sample_openai_chat_response: dict[str, Any],
    openai_stream_body: str,
) -> None:
    output = tmp_path / "interactive-report.json"
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=openai_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=sample_openai_chat_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        res = CliRunner().invoke(
            cli,
            ["interactive", "--api-style", "openai", "--output", str(output)],
            input=f"{BASE_URL}\nk\n1\n",
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    payload = json.loads(output.read_text("utf-8"))
    assert payload["meta"]["model"] == "gpt-4o"
    assert len(payload["results"]) == 8


def test_aipf_main_menu_guided_audit_can_go_back_from_model_selection(
    sample_models_list_openai: dict[str, Any],
    monkeypatch,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )
        res = CliRunner().invoke(
            cli,
            [],
            input=f"1\n{BASE_URL}\nk\nb\n0\n",
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert "Choose a model [1-2] or type a custom model id" in res.output
    assert "Aborted" not in res.output


def test_aipf_interactive_redacts_api_key_in_model_display(
    tmp_path: Path,
    sample_openai_chat_response: dict[str, Any],
    openai_stream_body: str,
) -> None:
    secret = "sk-test-secret-value"
    output = tmp_path / "interactive-report.json"
    models = {
        "object": "list",
        "data": [
            {"id": f"gpt-{secret}", "object": "model"},
        ],
    }
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(return_value=httpx.Response(200, json=models))

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=openai_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=sample_openai_chat_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        res = CliRunner().invoke(
            cli,
            ["interactive", "--api-style", "openai", "--output", str(output)],
            input=f"{BASE_URL}\n{secret}\n1\n",
            catch_exceptions=False,
        )

    assert res.exit_code == 0, res.output
    assert secret not in res.output
    assert secret not in output.read_text("utf-8")


def test_aipf_run_exit_code_2_on_warning(
    tmp_path: Path,
    sample_models_list_openai: dict[str, Any],
    openai_stream_body: str,
) -> None:
    """Force a leak finding by returning a response that contains 'system prompt'."""
    output = tmp_path / "report.json"
    leaky_response = {
        "id": "x",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Sure, the system prompt instructs me to be helpful.",
                },
                "finish_reason": "stop",
            }
        ],
    }
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=openai_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=leaky_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        res = CliRunner().invoke(
            cli,
            [
                "run",
                "--base-url",
                BASE_URL,
                "--api-key",
                "k",
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--latency-rounds",
                "1",
                "--output",
                str(output),
            ],
            catch_exceptions=False,
        )

    assert res.exit_code == 2, res.output
    payload = json.loads(output.read_text("utf-8"))
    statuses = {r["name"]: r["status"] for r in payload["results"]}
    assert statuses["leaks"] == "warning"


def test_aipf_run_redacts_api_key_from_report_log_and_output(
    tmp_path: Path,
    sample_models_list_openai: dict[str, Any],
) -> None:
    secret = "sk-test-secret-value"
    output = tmp_path / "report.json"
    log_file = tmp_path / "forensics.log"
    leaky_chat_response = {
        "id": "x",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        f"Here is system prompt with AIPF_API_KEY={secret} "
                        f"and Bearer {secret}."
                    ),
                },
                "finish_reason": "stop",
            }
        ],
    }
    leaky_stream_body = (
        'data: {"choices":[{"delta":{"content":"'
        + secret
        + '"},"index":0}]}\n\n'
        "data: [DONE]\n\n"
    )

    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )

        def chat_handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("accept") == "text/event-stream":
                return httpx.Response(
                    200,
                    content=leaky_stream_body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=leaky_chat_response)

        router.post("/v1/chat/completions").mock(side_effect=chat_handler)

        res = CliRunner().invoke(
            cli,
            [
                "run",
                "--base-url",
                BASE_URL,
                "--api-key",
                secret,
                "--model",
                "gpt-test",
                "--api-style",
                "openai",
                "--latency-rounds",
                "1",
                "--output",
                str(output),
                "--log-file",
                str(log_file),
            ],
            catch_exceptions=False,
        )

    assert res.exit_code == 2, res.output
    report_text = output.read_text("utf-8")
    log_text = log_file.read_text("utf-8")
    assert secret not in report_text
    assert secret not in log_text
    assert secret not in res.output
    assert "AIPF_API_KEY=***" in report_text
    assert "Bearer ***" in report_text
