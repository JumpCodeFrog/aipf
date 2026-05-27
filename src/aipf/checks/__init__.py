from __future__ import annotations

from aipf.checks import (
    completion,
    fingerprint,
    injection,
    latency,
    leaks,
    models_list,
    streaming,
    tool_ids,
)
from aipf.checks.base import CheckFn, RunContext

CHECK_REGISTRY: dict[str, CheckFn] = {
    models_list.NAME: models_list.run,
    completion.NAME: completion.run,
    streaming.NAME: streaming.run,
    injection.NAME: injection.run,
    leaks.NAME: leaks.run,
    fingerprint.NAME: fingerprint.run,
    tool_ids.NAME: tool_ids.run,
    latency.NAME: latency.run,
}

CHECK_ORDER: tuple[str, ...] = (
    models_list.NAME,
    completion.NAME,
    streaming.NAME,
    injection.NAME,
    leaks.NAME,
    fingerprint.NAME,
    tool_ids.NAME,
    latency.NAME,
)

__all__ = ["CHECK_REGISTRY", "CHECK_ORDER", "RunContext", "CheckFn"]
