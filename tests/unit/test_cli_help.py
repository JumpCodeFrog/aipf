from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from aipf import cli as cli_module
from aipf.cli import cli

EXPECTED_COMMANDS = (
    "run",
    "interactive",
    "models",
    "completion",
    "stream",
    "inject",
    "leaks",
    "fingerprint",
    "tool-ids",
    "latency",
    "replay",
)


def test_top_level_help_lists_commands() -> None:
    res = CliRunner().invoke(cli, ["--help"])
    assert res.exit_code == 0
    for cmd in EXPECTED_COMMANDS:
        assert cmd in res.output


def test_top_level_without_tty_prints_help() -> None:
    res = CliRunner().invoke(cli, [])

    assert res.exit_code == 0
    assert "Usage: cli [OPTIONS] COMMAND [ARGS]..." in res.output
    assert "run" in res.output
    assert "interactive" in res.output
    assert "Select" not in res.output


def test_top_level_tty_menu_can_show_help_and_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="5\n0\n")

    assert res.exit_code == 0, res.output
    assert "Main menu" in res.output or "aipf | main menu" in res.output
    assert "Guided audit" in res.output
    assert "Usage: cli [OPTIONS] COMMAND [ARGS]..." in res.output


def test_top_level_tty_guided_audit_can_go_back_from_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="1\nb\n0\n")

    assert res.exit_code == 0, res.output
    assert "Endpoint URL (Enter 'b' to go back, 'q' to quit.)" in res.output
    assert "Aborted" not in res.output
    assert "Traceback" not in res.output


def test_top_level_tty_guided_audit_can_quit_from_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="1\nhttps://mock.example.com\nq\n")

    assert res.exit_code == 0, res.output
    assert "API key (Enter 'b' to go back, 'q' to quit.)" in res.output
    assert "Aborted" not in res.output
    assert "Traceback" not in res.output


def test_top_level_tty_config_fallback_can_go_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="2\nb\n0\n")

    assert res.exit_code == 0, res.output
    assert "Missing required configuration:" in res.output
    assert "Start guided audit? [Y/n/b/q]" in res.output
    assert "Aborted" not in res.output


def test_top_level_tty_config_fallback_can_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="3\nq\n")

    assert res.exit_code == 0, res.output
    assert "Missing required configuration:" in res.output
    assert "Start guided audit? [Y/n/b/q]" in res.output
    assert "Aborted" not in res.output


def test_top_level_tty_replay_menu_can_go_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="4\nb\n0\n")

    assert res.exit_code == 0, res.output
    assert "Replay capture file. Enter a path" in res.output
    assert "Capture file" in res.output
    assert "Aborted" not in res.output
    assert "File 'b' does not exist" not in res.output


def test_top_level_tty_replay_menu_invalid_path_then_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="4\nmissing.json\nb\n0\n")

    assert res.exit_code == 0, res.output
    assert "File does not exist: missing.json" in res.output
    assert "Aborted" not in res.output


def test_top_level_tty_replay_menu_can_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)

    res = CliRunner().invoke(cli, [], input="4\nq\n")

    assert res.exit_code == 0, res.output
    assert "Replay capture file. Enter a path" in res.output
    assert "Aborted" not in res.output


def test_top_level_tty_replay_menu_renders_capture_and_returns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("aipf.cli._stdin_is_interactive", lambda: True)
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "meta": {
                    "tool": "aipf",
                    "tool_version": "0.1.0",
                    "python_version": "3.13.7",
                    "started_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:01Z",
                    "command": "completion",
                    "event_count": 1,
                    "truncated": False,
                    "max_events": 20000,
                    "max_bytes": 5000000,
                    "notes": [],
                },
                "events": [
                    {
                        "seq": 1,
                        "t_ms": 1.25,
                        "event": "http.request.end",
                        "fields": {"status": 200, "latency_ms": 12.3},
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        "utf-8",
    )

    res = CliRunner().invoke(cli, [], input=f"4\n{capture}\n0\n")

    assert res.exit_code == 0, res.output
    assert "capture schema=v1 command=completion" in res.output
    assert "http.request.end" in res.output
    assert "Aborted" not in res.output


@pytest.mark.parametrize("cmd", EXPECTED_COMMANDS)
def test_subcommand_help_exits_zero(cmd: str) -> None:
    res = CliRunner().invoke(cli, [cmd, "--help"])
    assert res.exit_code == 0, res.output
    if cmd == "interactive":
        assert "--timeout" in res.output
        assert "--pause" in res.output
        assert "--capture" in res.output
    elif cmd == "replay":
        assert "--format" in res.output
        return
    else:
        assert "--base-url" in res.output
        assert "--api-key" in res.output
        assert "--capture" in res.output
        assert "--artifacts-dir" in res.output
    assert "--debug" in res.output
    assert "--trace" in res.output
    assert "--debug-format" in res.output


def test_run_without_required_config_shows_usage_error() -> None:
    res = CliRunner().invoke(cli, ["run"])

    assert res.exit_code == 2
    assert "Missing required configuration:" in res.output
    assert "proxy base URL: pass --base-url or set AIPF_BASE_URL." in res.output
    assert "API key: pass --api-key or set AIPF_API_KEY." in res.output
    assert "For guided setup, run: aipf interactive" in res.output
    assert "Traceback" not in res.output
    assert "ValidationError" not in res.output


def test_run_without_api_key_only_mentions_api_key() -> None:
    res = CliRunner().invoke(cli, ["run", "--base-url", "https://mock.example.com"])

    assert res.exit_code == 2
    assert "API key: pass --api-key or set AIPF_API_KEY." in res.output
    assert "proxy base URL" not in res.output
    assert "Traceback" not in res.output


def test_run_with_blank_env_values_shows_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIPF_BASE_URL", "")
    monkeypatch.setenv("AIPF_API_KEY", "")
    monkeypatch.setenv("AIPF_MODEL", "gpt-test")

    res = CliRunner().invoke(cli, ["run"])

    assert res.exit_code == 2
    assert "Invalid configuration:" in res.output
    assert "proxy base URL: Value error, base URL cannot be empty." in res.output
    assert "API key: Value error, API key cannot be empty." in res.output
    assert "Traceback" not in res.output


def test_ci_env_forces_plain_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("FORCE_COLOR", "1")

    assert cli_module._plain_console() is True


@pytest.mark.parametrize("env_var", ("FORCE_PLAIN_OUTPUT", "AIPF_NO_COLOR"))
def test_plain_output_env_flags_force_plain_console(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
) -> None:
    monkeypatch.setenv(env_var, "1")

    assert cli_module._plain_console() is True
