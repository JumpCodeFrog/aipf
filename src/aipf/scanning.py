from __future__ import annotations

import re

from aipf.fingerprints import (
    ANTHROPIC_PATTERNS,
    OPENAI_PATTERNS,
    TOOL_PATTERNS,
    WRAPPER_LEAK_PHRASES,
)
from aipf.models import LeakFinding, ProviderFingerprint

SNIPPET_RADIUS = 60


def snippet(text: str, length: int = 3000) -> str:
    if len(text) <= length:
        return text
    return text[:length] + "…"


def scan_phrases(text: str, phrases: tuple[str, ...] = WRAPPER_LEAK_PHRASES) -> list[LeakFinding]:
    findings: list[LeakFinding] = []
    if not text:
        return findings
    lower = text.lower()
    for phrase in phrases:
        idx = lower.find(phrase.lower())
        if idx >= 0:
            start = max(0, idx - SNIPPET_RADIUS)
            end = min(len(text), idx + len(phrase) + SNIPPET_RADIUS)
            findings.append(
                LeakFinding(
                    phrase=phrase,
                    context_snippet=text[start:end],
                    position=idx,
                )
            )
    return findings


def compute_fingerprint(text: str) -> ProviderFingerprint:
    if not text:
        return ProviderFingerprint(verdict="unknown")
    lower = text.lower()
    matched_anth: list[str] = [p for p in ANTHROPIC_PATTERNS if p in lower]
    matched_oai: list[str] = [p for p in OPENAI_PATTERNS if p in lower]

    anthropic_score = len(matched_anth)
    openai_score = len(matched_oai)

    if anthropic_score == 0 and openai_score == 0:
        verdict: str = "unknown"
    elif anthropic_score > openai_score:
        verdict = "anthropic"
    elif openai_score > anthropic_score:
        verdict = "openai"
    else:
        verdict = "unknown"

    return ProviderFingerprint(
        anthropic_score=anthropic_score,
        openai_score=openai_score,
        verdict=verdict,  # type: ignore[arg-type]
        matched_patterns={"anthropic": matched_anth, "openai": matched_oai},
    )


def scan_tool_ids(text: str) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    if not text:
        return matches
    for provider, prefixes in TOOL_PATTERNS.items():
        found: list[str] = []
        for prefix in prefixes:
            pattern = re.compile(rf"{re.escape(prefix)}[A-Za-z0-9_-]+")
            for m in pattern.finditer(text):
                found.append(m.group(0))
        if found:
            matches[provider] = found
    return matches
