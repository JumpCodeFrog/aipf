from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(output: str) -> str:
    return _ANSI_RE.sub("", output)


def normalize_output(output: str) -> str:
    clean = strip_ansi(output)
    lines = [" ".join(line.split()) for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)


def safe_assert_output(output: str, expected: str) -> None:
    normalized = normalize_output(output)
    assert expected in normalized, normalized
