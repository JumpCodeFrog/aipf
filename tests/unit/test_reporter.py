from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from aipf.models import (
    ApiStyle,
    CheckStatus,
    CompletionResult,
    LeakFinding,
    LeakResult,
    ModelsListResult,
    StreamingResult,
)
from aipf.reporter import (
    build_report,
    default_report_path,
    exit_code_for,
    write_report,
)


def test_exit_code_for_all_passed() -> None:
    report = build_report(
        "http://x",
        "m",
        ApiStyle.OPENAI,
        [ModelsListResult(name="models", status=CheckStatus.PASSED, models=["a"], raw_count=1)],
        datetime.now(UTC),
        datetime.now(UTC),
    )
    assert exit_code_for(report) == 0


def test_exit_code_for_warning() -> None:
    report = build_report(
        "http://x",
        "m",
        ApiStyle.OPENAI,
        [
            ModelsListResult(name="models", status=CheckStatus.PASSED, models=["a"], raw_count=1),
            LeakResult(
                name="leaks",
                status=CheckStatus.WARNING,
                findings=[LeakFinding(phrase="x", context_snippet="x", position=0)],
            ),
        ],
        datetime.now(UTC),
        datetime.now(UTC),
    )
    assert exit_code_for(report) == 2


def test_exit_code_for_error_dominates() -> None:
    report = build_report(
        "http://x",
        "m",
        ApiStyle.OPENAI,
        [
            CompletionResult(name="c", status=CheckStatus.ERROR, error="boom"),
            LeakResult(name="leaks", status=CheckStatus.WARNING),
        ],
        datetime.now(UTC),
        datetime.now(UTC),
    )
    assert exit_code_for(report) == 1


def test_write_report_creates_valid_json(tmp_path: Path) -> None:
    report = build_report(
        "http://x",
        "m",
        ApiStyle.ANTHROPIC,
        [ModelsListResult(name="models", status=CheckStatus.PASSED, models=["a"], raw_count=1)],
        datetime.now(UTC),
        datetime.now(UTC),
    )
    path = tmp_path / "nested" / "out.json"
    write_report(report, path)
    payload = json.loads(path.read_text("utf-8"))
    assert payload["meta"]["api_style"] == "anthropic"
    assert payload["results"][0]["kind"] == "models_list"


def test_report_redacts_secret_without_changing_schema(tmp_path: Path) -> None:
    secret = "sk-test-secret-value"
    report = build_report(
        f"https://example.test/v1?api_key={secret}",
        "m",
        ApiStyle.OPENAI,
        [
            CompletionResult(
                name="completion",
                status=CheckStatus.PASSED,
                response_snippet=f"leaked bearer Bearer {secret}",
                http_calls=[],
            ),
            LeakResult(
                name="leaks",
                status=CheckStatus.WARNING,
                findings=[
                    LeakFinding(
                        phrase="system prompt",
                        context_snippet=f"system prompt contains AIPF_API_KEY={secret}",
                        position=0,
                    )
                ],
                response_snippet=f"api_key={secret}",
            ),
            StreamingResult(
                name="streaming",
                status=CheckStatus.PASSED,
                sample_chunks=[f'data: {{"delta":"{secret}"}}'],
            ),
        ],
        datetime.now(UTC),
        datetime.now(UTC),
        sensitive_values=(secret,),
    )
    path = tmp_path / "out.json"
    write_report(report, path, sensitive_values=(secret,))
    raw = path.read_text("utf-8")
    payload = json.loads(raw)

    assert secret not in raw
    assert payload["meta"]["base_url"].endswith("api_key=***")
    assert payload["results"][0]["response_snippet"] == "leaked bearer Bearer ***"
    assert payload["results"][1]["findings"][0]["context_snippet"].endswith(
        "AIPF_API_KEY=***"
    )
    assert payload["results"][2]["sample_chunks"] == ['data: {"delta":"***"}']


def test_default_report_path_has_timestamp() -> None:
    path = default_report_path()
    name = path.name
    assert path.parent.as_posix() == "aipf-artifacts/reports"
    assert name.startswith("report-") and name.endswith(".json")
