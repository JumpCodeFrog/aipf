from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, CompletionResult
from aipf.prompts import BASIC_COMPLETION_PROMPT
from aipf.scanning import snippet

logger = logging.getLogger(__name__)
NAME = "completion"


async def run(client: AsyncProxyClient, ctx: RunContext) -> CompletionResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})
    try:
        result = await client.chat(ctx.model, BASIC_COMPLETION_PROMPT)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("check.error")
        return CompletionResult(
            name=NAME,
            status=CheckStatus.ERROR,
            started_at=started_at,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )

    duration_ms = (time.perf_counter() - start) * 1000
    if 200 <= result.status_code < 300 and result.text:
        status = CheckStatus.PASSED
    elif 200 <= result.status_code < 300:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.FAILED

    latency_ms = result.calls[-1].latency_ms if result.calls else duration_ms
    logger.info(
        "check.end",
        extra={
            "event": "check.end",
            "check": NAME,
            "status": status.value,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return CompletionResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=result.calls,
        response_snippet=snippet(result.text, ctx.snippet_max_chars),
        tokens_estimate=max(1, len(result.text.split())) if result.text else 0,
        latency_ms=latency_ms,
        details={"http_status": result.status_code},
    )
