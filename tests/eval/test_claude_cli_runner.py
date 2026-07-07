"""Tests for the shared subprocess wrapper around `claude -p`."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from scripts.eval import claude_cli_runner
from scripts.eval.claude_cli_runner import run_claude_cli
from scripts.eval.errors import ClaudeCliError


def _ok_payload(text: str = "hello", **usage_overrides) -> str:
    usage = {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    usage.update(usage_overrides)
    return json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": text,
            "usage": usage,
            "modelUsage": {"claude-sonnet-5": {"inputTokens": 10}},
            "total_cost_usd": 0.001,
        }
    )


def _fake_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class _Recorder:
    """Captures the subprocess.run call so assertions can inspect cmd + input."""

    def __init__(self, response):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture(autouse=True)
def _ensure_claude_on_path(monkeypatch):
    monkeypatch.setattr(claude_cli_runner.shutil, "which", lambda _: "/usr/bin/claude")


# ---- happy path ----------------------------------------------------------


def test_runs_and_parses_usage() -> None:
    rec = _Recorder(_fake_completed(stdout=_ok_payload("hi", cache_read_input_tokens=128)))
    result = run_claude_cli(
        prompt="say hi",
        system_prompt="be brief",
        model="claude-sonnet-5",
        runner=rec,
    )
    assert result.text == "hi"
    assert result.usage.cache_read_input_tokens == 128
    assert result.cost_usd == pytest.approx(0.001)
    assert result.model == "claude-sonnet-5"


def test_prompt_is_piped_via_stdin_not_argv() -> None:
    """Large prompts must not blow ARG_MAX, so we pass them via stdin."""
    rec = _Recorder(_fake_completed(stdout=_ok_payload()))
    run_claude_cli(prompt="HUGE PROMPT", system_prompt="s", model="m", runner=rec)
    call = rec.calls[0]
    assert call["kwargs"]["input"] == "HUGE PROMPT"
    # argv carries only flags + system prompt, not the user prompt body.
    assert "HUGE PROMPT" not in call["cmd"]


def test_command_includes_disallowed_tools_and_system_prompt() -> None:
    rec = _Recorder(_fake_completed(stdout=_ok_payload()))
    run_claude_cli(prompt="p", system_prompt="SYS-MARKER", model="claude-haiku-4-5", runner=rec)
    cmd = rec.calls[0]["cmd"]
    # `--system-prompt SYS-MARKER` adjacency
    idx = cmd.index("--system-prompt")
    assert cmd[idx + 1] == "SYS-MARKER"
    # tools list present and contains a few known names
    idx = cmd.index("--disallowed-tools")
    tools = cmd[idx + 1]
    for name in ("Bash", "Read", "WebFetch", "Edit"):
        assert name in tools


def test_extra_args_are_appended() -> None:
    rec = _Recorder(_fake_completed(stdout=_ok_payload()))
    run_claude_cli(
        prompt="p", system_prompt="s", model="m", extra_args=["--max-budget-usd", "1"], runner=rec
    )
    cmd = rec.calls[0]["cmd"]
    assert cmd[-2:] == ["--max-budget-usd", "1"]


# ---- error paths ---------------------------------------------------------


def test_missing_cli_raises(monkeypatch) -> None:
    monkeypatch.setattr(claude_cli_runner.shutil, "which", lambda _: None)
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="m")
    assert "not on PATH" in str(exc.value)


def test_timeout_is_mapped_to_cli_error() -> None:
    rec = _Recorder(subprocess.TimeoutExpired(cmd="claude", timeout=1))
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="m", timeout_sec=1, runner=rec)
    assert "timed out" in str(exc.value)


def test_nonzero_exit_raises_with_stderr_snippet() -> None:
    rec = _Recorder(_fake_completed(stdout="", stderr="boom!", returncode=2))
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="m", runner=rec)
    assert "exited 2" in str(exc.value)
    assert "boom" in str(exc.value)


def test_invalid_json_stdout_raises() -> None:
    rec = _Recorder(_fake_completed(stdout="not json"))
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="m", runner=rec)
    assert "not valid JSON" in str(exc.value)


def test_is_error_true_raises_with_detail() -> None:
    payload = json.dumps(
        {
            "is_error": True,
            "api_error_status": 404,
            "result": "There's an issue with the selected model (bogus). It may not exist.",
            "usage": {},
        }
    )
    rec = _Recorder(_fake_completed(stdout=payload))
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="bogus", runner=rec)
    msg = str(exc.value)
    assert "is_error=true" in msg
    assert "404" in msg
    assert "bogus" in msg


def test_missing_result_field_raises() -> None:
    payload = json.dumps({"is_error": False, "usage": {}})
    rec = _Recorder(_fake_completed(stdout=payload))
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="m", runner=rec)
    assert "missing `result`" in str(exc.value)


def test_spawn_filenotfound_raises_cli_error() -> None:
    rec = _Recorder(FileNotFoundError("vanished"))
    with pytest.raises(ClaudeCliError) as exc:
        run_claude_cli(prompt="p", system_prompt="s", model="m", runner=rec)
    assert "failed to spawn" in str(exc.value)


def test_missing_usage_section_is_zeroed_not_an_error() -> None:
    """The CLI emits a `usage` block even on success; tolerate it being absent."""
    payload = json.dumps({"is_error": False, "result": "ok"})
    rec = _Recorder(_fake_completed(stdout=payload))
    res = run_claude_cli(prompt="p", system_prompt="s", model="m", runner=rec)
    assert res.usage.input_tokens == 0
    assert res.usage.output_tokens == 0
