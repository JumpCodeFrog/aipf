from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

REDACTED = "***"
MIN_EXACT_SECRET_LENGTH = 8

_SENSITIVE_KEY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "bearer_token",
    "secret",
    "token",
    "x_api_key",
}

_KEY_VALUE_RE = re.compile(
    r"""(?ix)
    (["']?
      (?:aipf_api_key|api[-_]?key|x[-_]?api[-_]?key|authorization|access_token|token)
      ["']?\s*[:=]\s*["']?
    )
    (?:bearer\s+)?
    ([^"',\s}\]]+)
    (["']?)
    """
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+(?!bearer\b)[A-Za-z0-9._~+/=-]{6,}")
_URL_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[-_]?key|key|token|access_token)=)[^&#\s\"',}\]]+"
)
_URL_USERINFO_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/?#\s@]+@)")
_OPENAI_STYLE_KEY_RE = re.compile(r"(?i)\bsk-[A-Za-z0-9][A-Za-z0-9_-]{7,}\b")


def redact_text(text: str, sensitive_values: Iterable[str] = ()) -> str:
    """Redact known secret shapes and caller-provided exact secret values."""
    if not text:
        return text

    redacted = text
    for secret in _normalized_sensitive_values(sensitive_values):
        redacted = redacted.replace(secret, REDACTED)

    redacted = _KEY_VALUE_RE.sub(_replace_key_value, redacted)
    redacted = _BEARER_RE.sub("Bearer " + REDACTED, redacted)
    redacted = _URL_QUERY_SECRET_RE.sub(r"\1" + REDACTED, redacted)
    redacted = _URL_USERINFO_RE.sub(r"\1" + REDACTED + "@", redacted)
    return _OPENAI_STYLE_KEY_RE.sub(REDACTED, redacted)


def redact_data(value: Any, sensitive_values: Iterable[str] = ()) -> Any:
    """Recursively redact strings and sensitive mapping values."""
    return _redact_data(value, _normalized_sensitive_values(sensitive_values))


def is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.lower().replace("-", "_")
    return (
        normalized in _SENSITIVE_KEY_NAMES
        or normalized.endswith("_api_key")
        or "authorization" in normalized
    )


def _redact_data(value: Any, sensitive_values: tuple[str, ...]) -> Any:
    result: Any
    if isinstance(value, str):
        result = redact_text(value, sensitive_values)
    elif isinstance(value, Mapping):
        result = {
            key: REDACTED if is_sensitive_key(key) else _redact_data(item, sensitive_values)
            for key, item in value.items()
        }
    elif isinstance(value, list):
        result = [_redact_data(item, sensitive_values) for item in value]
    elif isinstance(value, tuple):
        result = tuple(_redact_data(item, sensitive_values) for item in value)
    else:
        result = value
    return result


def _normalized_sensitive_values(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if len(value) < MIN_EXACT_SECRET_LENGTH or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(sorted(normalized, key=len, reverse=True))


def _replace_key_value(match: re.Match[str]) -> str:
    return f"{match.group(1)}{REDACTED}{match.group(3)}"
