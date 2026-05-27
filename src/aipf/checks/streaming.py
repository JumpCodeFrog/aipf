from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, StreamingResult
from aipf.prompts import STREAMING_PROMPT

logger = logging.getLogger(__name__)
NAME = "streaming"


async def run(client: AsyncProxyClient, ctx: RunContext) -> StreamingResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})
    try:
        result = await client.chat_stream(ctx.model, STREAMING_PROMPT)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("check.error")
        return StreamingResult(
            name=NAME,
            status=CheckStatus.ERROR,
            started_at=started_at,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )

    duration_ms = (time.perf_counter() - start) * 1000
    if result.sse_format_valid and result.chunk_count > 0:
        status = CheckStatus.PASSED
    elif result.chunk_count > 0:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.FAILED

    logger.info(
        "check.end",
        extra={
            "event": "check.end",
            "check": NAME,
            "status": status.value,
            "duration_ms": round(duration_ms, 2),
            "chunks": result.chunk_count,
            "first_chunk_ms": round(result.first_chunk_ms, 2),
        },
    )
    return StreamingResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=result.calls,
        chunk_count=result.chunk_count,
        first_chunk_ms=result.first_chunk_ms,
        total_ms=result.total_ms,
        sse_format_valid=result.sse_format_valid,
        sample_chunks=result.sample_chunks,
    )
