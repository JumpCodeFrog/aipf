from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aipf.models import (
    ApiStyle,
    CheckStatus,
    CompletionResult,
    InjectionAttempt,
    InjectionResult,
    LatencyResult,
    LatencyStats,
    LeakFinding,
    LeakResult,
    ModelsListResult,
    ProviderFingerprint,
    RunMeta,
    RunReport,
)


def _meta() -> RunMeta:
    now = datetime.now(UTC)
    return RunMeta(
        started_at=now,
        finished_at=now,
        base_url="https://example.com",
        model="test",
        api_style=ApiStyle.OPENAI,
        tool_version="0.1.0",
        python_version="3.13.7",
    )


def test_models_list_result_defaults() -> None:
    r = ModelsListResult(name="models_list", status=CheckStatus.PASSED)
    assert r.kind == "models_list"
    assert r.models == []
    assert r.raw_count == 0


def test_run_report_discriminator_round_trip() -> None:
    report = RunReport(
        meta=_meta(),
        results=[
            ModelsListResult(name="models", status=CheckStatus.PASSED, models=["a"], raw_count=1),
            CompletionResult(name="completion", status=CheckStatus.PASSED, response_snippet="hi"),
            LeakResult(
                name="leaks",
                status=CheckStatus.WARNING,
                findings=[LeakFinding(phrase="x", context_snippet="...x...", position=3)],
            ),
            InjectionResult(
                name="injection",
                status=CheckStatus.PASSED,
                attempts=[
                    InjectionAttempt(
                        attack_name="probe", attack_prompt="?", response_snippet="ok"
                    )
                ],
            ),
            LatencyResult(
                name="latency",
                status=CheckStatus.PASSED,
                stats=LatencyStats(
                    count=2,
                    min_ms=10,
                    max_ms=20,
                    mean_ms=15,
                    median_ms=15,
                    p95_ms=20,
                    stddev_ms=5,
                ),
                samples_ms=[10, 20],
            ),
        ],
    )
    js = report.model_dump_json()
    parsed = RunReport.model_validate_json(js)
    kinds = [r.kind for r in parsed.results]
    assert kinds == ["models_list", "completion", "leaks", "injection", "latency"]
    leak = parsed.results[2]
    assert isinstance(leak, LeakResult)
    assert leak.findings[0].phrase == "x"


def test_provider_fingerprint_defaults() -> None:
    fp = ProviderFingerprint()
    assert fp.verdict == "unknown"
    assert fp.anthropic_score == 0


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        LeakFinding(phrase="a", context_snippet="b", position=0, extra="x")  # type: ignore[call-arg]
