from __future__ import annotations

import logging
import statistics
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, HttpCallLog, LatencyResult, LatencyStats
from aipf.prompts import LATENCY_PROMPT

logger = logging.getLogger(__name__)
NAME = "latency"


async def run(client: AsyncProxyClient, ctx: RunContext) -> LatencyResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})

    samples_ms: list[float] = []
    all_calls: list[HttpCallLog] = []
    error: str | None = None
    rounds = max(1, ctx.latency_rounds)

    for i in range(rounds):
        round_start = time.perf_counter()
        client.trace("latency.round.start", round=i + 1, total_rounds=rounds)
        try:
            result = await client.chat(ctx.model, LATENCY_PROMPT, max_tokens=32)
        except Exception as exc:
            error = error or f"{type(exc).__name__}: {exc}"
            client.trace(
                "latency.round.error",
                round=i + 1,
                total_rounds=rounds,
                elapsed_ms=round((time.perf_counter() - round_start) * 1000, 2),
                error=error,
            )
            logger.exception("latency.round.error", extra={"round": i + 1})
            continue
        all_calls.extend(result.calls)
        sample_ms = result.calls[-1].latency_ms if result.calls else None
        client.trace(
            "latency.round.end",
            round=i + 1,
            total_rounds=rounds,
            elapsed_ms=round((time.perf_counter() - round_start) * 1000, 2),
            sample_ms=round(sample_ms, 2) if sample_ms is not None else None,
            status=result.status_code,
        )
        if result.calls:
            samples_ms.append(result.calls[-1].latency_ms)

    duration_ms = (time.perf_counter() - start) * 1000
    stats = _compute_stats(samples_ms)
    client.trace(
        "latency.summary",
        samples=len(samples_ms),
        total_rounds=rounds,
        mean_ms=round(stats.mean_ms, 2) if stats else None,
        p95_ms=round(stats.p95_ms, 2) if stats else None,
        min_ms=round(stats.min_ms, 2) if stats else None,
        max_ms=round(stats.max_ms, 2) if stats else None,
    )

    if not samples_ms and error:
        status = CheckStatus.ERROR
    elif not samples_ms:
        status = CheckStatus.FAILED
    elif len(samples_ms) < rounds:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.PASSED

    logger.info(
        "check.end",
        extra={
            "event": "check.end",
            "check": NAME,
            "status": status.value,
            "duration_ms": round(duration_ms, 2),
            "samples": len(samples_ms),
            "mean_ms": round(stats.mean_ms, 2) if stats else None,
        },
    )
    return LatencyResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=all_calls,
        stats=stats,
        samples_ms=samples_ms,
        error=error,
    )


def _compute_stats(samples: list[float]) -> LatencyStats | None:
    if not samples:
        return None
    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    if n == 1:
        only = sorted_samples[0]
        return LatencyStats(
            count=1,
            min_ms=only,
            max_ms=only,
            mean_ms=only,
            median_ms=only,
            p95_ms=only,
            stddev_ms=0.0,
        )
    p95_idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
    return LatencyStats(
        count=n,
        min_ms=sorted_samples[0],
        max_ms=sorted_samples[-1],
        mean_ms=statistics.fmean(sorted_samples),
        median_ms=statistics.median(sorted_samples),
        p95_ms=sorted_samples[p95_idx],
        stddev_ms=statistics.pstdev(sorted_samples),
    )
