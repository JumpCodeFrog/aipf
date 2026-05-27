from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


class ApiStyle(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class SignalStrength(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class ImpersonationVerdict(StrEnum):
    CONSISTENT = "consistent"
    SUSPICIOUS = "suspicious"
    LIKELY_IMPERSONATION = "likely_impersonation"
    UNKNOWN = "unknown"


class MismatchSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class HttpCallLog(_Strict):
    method: str
    url: str
    status_code: int | None = None
    latency_ms: float
    attempt: int = 1
    request_id: str | None = None
    error: str | None = None


class LeakFinding(_Strict):
    phrase: str
    context_snippet: str
    position: int


class ProviderFingerprint(_Strict):
    anthropic_score: int = 0
    openai_score: int = 0
    verdict: Literal["anthropic", "openai", "unknown"] = "unknown"
    matched_patterns: dict[str, list[str]] = Field(default_factory=dict)


class IdentityClaim(_Strict):
    provider: str | None = None
    model: str | None = None
    model_family: str | None = None
    source: str
    quote: str
    normalized: str | None = None
    polarity: Literal["positive", "negative", "uncertain"] = "positive"


class IdentitySignal(_Strict):
    type: str
    strength: SignalStrength
    provider_hint: str | None = None
    model_family_hint: str | None = None
    weight: float
    confidence_delta: float = 0.0
    source_check: str
    evidence_snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MismatchFlag(_Strict):
    code: str
    severity: MismatchSeverity
    message: str


class ImpersonationAssessment(_Strict):
    claimed_provider: str | None = None
    claimed_model: str | None = None
    likely_provider: str | None = None
    likely_model_family: str | None = None
    confidence: float = 0.0
    impersonation_score: float = 0.0
    signal_breakdown: list[IdentitySignal] = Field(default_factory=list)
    mismatch_flags: list[MismatchFlag] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    verdict: ImpersonationVerdict = ImpersonationVerdict.UNKNOWN
    claims: list[IdentityClaim] = Field(default_factory=list)
    provider_scores: dict[str, float] = Field(default_factory=dict)
    model_family_scores: dict[str, float] = Field(default_factory=dict)


class LatencyStats(_Strict):
    count: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float
    stddev_ms: float


class _ResultBase(_Strict):
    name: str
    status: CheckStatus
    started_at: datetime = Field(default_factory=_utcnow)
    duration_ms: float = 0.0
    http_calls: list[HttpCallLog] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ModelsListResult(_ResultBase):
    kind: Literal["models_list"] = "models_list"
    models: list[str] = Field(default_factory=list)
    raw_count: int = 0


class CompletionResult(_ResultBase):
    kind: Literal["completion"] = "completion"
    response_snippet: str = ""
    tokens_estimate: int = 0
    latency_ms: float = 0.0


class StreamingResult(_ResultBase):
    kind: Literal["streaming"] = "streaming"
    chunk_count: int = 0
    first_chunk_ms: float = 0.0
    total_ms: float = 0.0
    sse_format_valid: bool = False
    sample_chunks: list[str] = Field(default_factory=list)


class InjectionAttempt(_Strict):
    attack_name: str
    attack_prompt: str
    response_snippet: str
    triggered_leaks: list[LeakFinding] = Field(default_factory=list)


class InjectionResult(_ResultBase):
    kind: Literal["injection"] = "injection"
    attempts: list[InjectionAttempt] = Field(default_factory=list)


class LeakResult(_ResultBase):
    kind: Literal["leaks"] = "leaks"
    findings: list[LeakFinding] = Field(default_factory=list)
    response_snippet: str = ""


class FingerprintResult(_ResultBase):
    kind: Literal["fingerprint"] = "fingerprint"
    fingerprint: ProviderFingerprint = Field(default_factory=ProviderFingerprint)
    response_snippet: str = ""


class ToolIdResult(_ResultBase):
    kind: Literal["tool_ids"] = "tool_ids"
    matches: dict[str, list[str]] = Field(default_factory=dict)
    response_snippet: str = ""


class ImpersonationResult(_ResultBase):
    kind: Literal["impersonation"] = "impersonation"
    assessment: ImpersonationAssessment = Field(default_factory=ImpersonationAssessment)


class LatencyResult(_ResultBase):
    kind: Literal["latency"] = "latency"
    stats: LatencyStats | None = None
    samples_ms: list[float] = Field(default_factory=list)


TestResult = Annotated[
    ModelsListResult
    | CompletionResult
    | StreamingResult
    | InjectionResult
    | LeakResult
    | FingerprintResult
    | ToolIdResult
    | ImpersonationResult
    | LatencyResult,
    Field(discriminator="kind"),
]


class RunMeta(_Strict):
    started_at: datetime
    finished_at: datetime
    base_url: str
    model: str
    api_style: ApiStyle
    tool_version: str
    python_version: str


class RunReport(_Strict):
    meta: RunMeta
    results: list[TestResult] = Field(default_factory=list)
