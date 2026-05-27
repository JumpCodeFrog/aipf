from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, ToolIdResult
from aipf.prompts import TOOLS_TEST
from aipf.scanning import scan_tool_ids, snippet

logger = logging.getLogger(__name__)
NAME = "tool_ids"


async def run(client: AsyncProxyClient, ctx: RunContext) -> ToolIdResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})
    try:
        result = await client.chat(ctx.model, TOOLS_TEST.prompt)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("check.error")
        return ToolIdResult(
            name=NAME,
            status=CheckStatus.ERROR,
            started_at=started_at,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )

    matches = scan_tool_ids(result.text)
    duration_ms = (time.perf_counter() - start) * 1000
    status = CheckStatus.WARNING if matches else CheckStatus.PASSED
    logger.info(
        "check.end",
        extra={
            "event": "check.end",
            "check": NAME,
            "status": status.value,
            "duration_ms": round(duration_ms, 2),
            "match_providers": list(matches.keys()),
        },
    )
    return ToolIdResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=result.calls,
        matches=matches,
        response_snippet=snippet(result.text, ctx.snippet_max_chars),
    )
