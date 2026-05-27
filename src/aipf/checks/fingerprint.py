from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, FingerprintResult
from aipf.prompts import IDENTITY_TEST
from aipf.scanning import compute_fingerprint, snippet

logger = logging.getLogger(__name__)
NAME = "fingerprint"


async def run(client: AsyncProxyClient, ctx: RunContext) -> FingerprintResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})
    try:
        result = await client.chat(ctx.model, IDENTITY_TEST.prompt)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("check.error")
        return FingerprintResult(
            name=NAME,
            status=CheckStatus.ERROR,
            started_at=started_at,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )

    fp = compute_fingerprint(result.text)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "check.end",
        extra={
            "event": "check.end",
            "check": NAME,
            "status": CheckStatus.PASSED.value,
            "duration_ms": round(duration_ms, 2),
            "verdict": fp.verdict,
        },
    )
    return FingerprintResult(
        name=NAME,
        status=CheckStatus.PASSED,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=result.calls,
        fingerprint=fp,
        response_snippet=snippet(result.text, ctx.snippet_max_chars),
    )
