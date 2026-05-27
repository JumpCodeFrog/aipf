from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, LeakResult
from aipf.prompts import SYSTEM_PROMPT_EXTRACTION
from aipf.scanning import scan_phrases, snippet

logger = logging.getLogger(__name__)
NAME = "leaks"


async def run(client: AsyncProxyClient, ctx: RunContext) -> LeakResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})
    try:
        result = await client.chat(ctx.model, SYSTEM_PROMPT_EXTRACTION.prompt)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("check.error")
        return LeakResult(
            name=NAME,
            status=CheckStatus.ERROR,
            started_at=started_at,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )

    findings = scan_phrases(result.text)
    duration_ms = (time.perf_counter() - start) * 1000
    status = CheckStatus.WARNING if findings else CheckStatus.PASSED

    logger.info(
        "check.end",
        extra={
            "event": "check.end",
            "check": NAME,
            "status": status.value,
            "duration_ms": round(duration_ms, 2),
            "findings": len(findings),
        },
    )
    return LeakResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=result.calls,
        findings=findings,
        response_snippet=snippet(result.text, ctx.snippet_max_chars),
    )
