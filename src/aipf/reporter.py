from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from aipf import __version__
from aipf.checks.base import TestResultUnion
from aipf.models import ApiStyle, CheckStatus, RunMeta, RunReport
from aipf.redaction import redact_data

ARTIFACTS_DIR = Path("aipf-artifacts")
REPORTS_DIR = ARTIFACTS_DIR / "reports"
LOGS_DIR = ARTIFACTS_DIR / "logs"
CAPTURES_DIR = ARTIFACTS_DIR / "captures"


def build_report(
    base_url: str,
    model: str,
    api_style: ApiStyle,
    results: list[TestResultUnion],
    started_at: datetime,
    finished_at: datetime,
    sensitive_values: tuple[str, ...] = (),
) -> RunReport:
    meta = RunMeta(
        started_at=started_at,
        finished_at=finished_at,
        base_url=base_url,
        model=model,
        api_style=api_style,
        tool_version=__version__,
        python_version=".".join(str(v) for v in sys.version_info[:3]),
    )
    report = RunReport(meta=meta, results=list(results))
    payload = cast(dict[str, Any], redact_data(report.model_dump(mode="json"), sensitive_values))
    return RunReport.model_validate(payload)


def write_report(
    report: RunReport,
    path: Path,
    sensitive_values: tuple[str, ...] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = redact_data(report.model_dump(mode="json"), sensitive_values)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def default_report_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return REPORTS_DIR / f"report-{stamp}.json"


def default_log_path() -> Path:
    return LOGS_DIR / "forensics.log"


def exit_code_for(report: RunReport) -> int:
    has_error = any(r.status is CheckStatus.ERROR for r in report.results)
    has_warning = any(r.status is CheckStatus.WARNING for r in report.results)
    if has_error:
        return 1
    if has_warning:
        return 2
    return 0
