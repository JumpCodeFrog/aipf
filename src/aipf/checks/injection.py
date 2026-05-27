from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from aipf.checks.base import RunContext
from aipf.client import AsyncProxyClient
from aipf.models import CheckStatus, HttpCallLog, InjectionAttempt, InjectionResult
from aipf.prompts import INJECTION_BATTERY
from aipf.scanning import scan_phrases, snippet

logger = logging.getLogger(__name__)
NAME = "injection"


async def run(client: AsyncProxyClient, ctx: RunContext) -> InjectionResult:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    logger.info("check.start", extra={"event": "check.start", "check": NAME})

    attempts: list[InjectionAttempt] = []
    all_calls: list[HttpCallLog] = []
    error: str | None = None

    for attack in INJECTION_BATTERY:
        try:
            result = await client.chat(ctx.model, attack.prompt)
        except Exception as exc:
            logger.exception("injection.error", extra={"attack": attack.name})
            error = error or f"{type(exc).__name__}: {exc}"
            attempts.append(
                InjectionAttempt(
                    attack_name=attack.name,
                    attack_prompt=attack.prompt,
                    response_snippet="",
                    triggered_leaks=[],
                )
            )
            continue
        all_calls.extend(result.calls)
        findings = scan_phrases(result.text)
        attempts.append(
            InjectionAttempt(
                attack_name=attack.name,
                attack_prompt=attack.prompt,
                response_snippet=snippet(result.text, ctx.snippet_max_chars),
                triggered_leaks=findings,
            )
        )

    duration_ms = (time.perf_counter() - start) * 1000
    any_leaks = any(a.triggered_leaks for a in attempts)
    if error and not any_leaks:
        status = CheckStatus.ERROR
    elif any_leaks:
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
            "leaks_total": sum(len(a.triggered_leaks) for a in attempts),
        },
    )
    return InjectionResult(
        name=NAME,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        http_calls=all_calls,
        attempts=attempts,
        error=error,
    )
