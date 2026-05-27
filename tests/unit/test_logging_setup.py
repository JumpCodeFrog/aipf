from __future__ import annotations

import json
import logging
from pathlib import Path

from rich.logging import RichHandler

from aipf.logging_setup import configure

SECRET = "sk-test-secret-value"


def test_json_logging_redacts_message_args_and_extras(tmp_path: Path) -> None:
    log_file = tmp_path / "forensics.log"
    configure(log_file=log_file, sensitive_values=(SECRET,))
    logger = logging.getLogger("aipf.test")

    logger.info(
        "request failed for Bearer %s",
        SECRET,
        extra={
            "api_key": SECRET,
            "headers": {"Authorization": f"Bearer {SECRET}"},
            "url": f"https://example.test/v1/models?api_key={SECRET}",
        },
    )

    line = log_file.read_text("utf-8").strip()
    payload = json.loads(line)

    assert SECRET not in line
    assert payload["api_key"] == "***"
    assert payload["headers"]["Authorization"] == "***"
    assert payload["url"].endswith("api_key=***")
    assert "Bearer ***" in payload["message"]


def test_console_logging_is_quiet_without_verbose(tmp_path: Path) -> None:
    log_file = tmp_path / "forensics.log"
    configure(log_file=log_file)
    rich_handlers = [
        handler for handler in logging.getLogger().handlers if isinstance(handler, RichHandler)
    ]

    assert len(rich_handlers) == 1
    assert rich_handlers[0].level == logging.WARNING

    logging.getLogger("aipf.test").info("quiet in console, present in file")

    assert "quiet in console" in log_file.read_text("utf-8")
