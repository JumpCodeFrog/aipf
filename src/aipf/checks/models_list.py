from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, ModelsListResult

logger = logging.getLogger(__name__)
NAME = "models_list"


async def run(client: AsyncProxyClient, ctx: RunContext) -> ModelsListResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})
    try:
        result = await client.list_models()
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("check.error")
        return ModelsListResult(
            name=NAME,
            status=CheckStatus.ERROR,
            started_at=started_at,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )

    duration_ms = (time.perf_counter() - start) * 1000
    if 200 <= result.status_code < 300 and result.ids:
        status = CheckStatus.PASSED
    elif 200 <= result.status_code < 300:
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
            "model_count": len(result.ids),
        },
    )
    return ModelsListResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=result.calls,
        models=result.ids,
        raw_count=len(result.ids),
        details={"http_status": result.status_code},
    )
