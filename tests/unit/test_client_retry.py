from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from aipf import client as client_module
from aipf.client import _parse_retry_after


def test_parse_retry_after_seconds() -> None:
    assert _parse_retry_after("2.5") == 2.5


def test_parse_retry_after_caps_large_values() -> None:
    assert _parse_retry_after("120") == client_module.MAX_RETRY_SLEEP_S


def test_parse_retry_after_clamps_negative_values() -> None:
    assert _parse_retry_after("-1") == 0.0


def test_parse_retry_after_http_date() -> None:
    future = datetime.now(UTC) + timedelta(seconds=10)

    delay = _parse_retry_after(format_datetime(future, usegmt=True))

    assert delay is not None
    assert 0.0 < delay <= 10.0


def test_parse_retry_after_invalid() -> None:
    assert _parse_retry_after("not a retry date") is None
