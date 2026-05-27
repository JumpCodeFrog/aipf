from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aipf.client import AsyncProxyClient
from aipf.models import (
    CompletionResult,
    FingerprintResult,
    InjectionResult,
    LatencyResult,
    LeakResult,
    ModelsListResult,
    StreamingResult,
    ToolIdResult,
)

TestResultUnion = (
    ModelsListResult
    | CompletionResult
    | StreamingResult
    | InjectionResult
    | LeakResult
    | FingerprintResult
    | ToolIdResult
    | LatencyResult
)


@dataclass
class RunContext:
    model: str
    latency_rounds: int = 5
    snippet_max_chars: int = 3000


CheckFn = Callable[[AsyncProxyClient, RunContext], Awaitable[TestResultUnion]]
