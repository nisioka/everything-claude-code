"""Tests for ClaudeCliExecutor — drives `claude -p` via the shared runner."""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.eval import claude_cli_runner
from scripts.eval.errors import ClaudeCliError
from scripts.eval.executors.claude_cli import ClaudeCliExecutor


def _ok_payload(text: str = "feat: add x", **usage_overrides) -> str:
    usage = {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    usage.update(usage_overrides)
    return json.dumps({"is_error": False, "result": text, "usage": usage})


def _fake_completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class _Recorder:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[dict] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        return _fake_completed(stdout=self.stdout, returncode=self.returncode)


@pytest.fixture(autouse=True)
def _ensure_claude_on_path(monkeypatch):
    monkeypatch.setattr(claude_cli_runner.shutil, "which", lambda _: "/usr/bin/claude")


def _build_executor(recorder: _Recorder) -> ClaudeCliExecutor:
    """Build an executor whose CLI calls land on the recorder.

    `run_claude_cli` ignores the executor's runner arg by default, so we monkeypatch
    `subprocess.run` (which the runner uses) at the module level.
    """
    return ClaudeCliExecutor(model="claude-sonnet-4-6")


# ---- system prompt assembly ------------------------------------------------


def test_run_passes_skill_and_instructions_as_single_system_prompt(monkeypatch) -> None:
    rec = _Recorder(stdout=_ok_payload("feat: add x", cache_creation_input_tokens=4096))
    monkeypatch.setattr(claude_cli_runner.subprocess, "run", rec)

    ex = _build_executor(rec)
    result = ex.run(
        prompt="generate commit",
        system_instructions="Be terse.",
        skill_markdown="# SKILL\nDo X.",
    )

    assert result.output == "feat: add x"
    cmd = rec.calls[0]["cmd"]
    idx = cmd.index("--system-prompt")
    sys_value = cmd[idx + 1]
    assert "Be terse." in sys_value
    assert "# SKILL" in sys_value
    # instructions come before the skill body
    assert sys_value.index("Be terse.") < sys_value.index("# SKILL")


def test_run_falls_back_when_no_instructions_or_skill(monkeypatch) -> None:
    rec = _Recorder(stdout=_ok_payload("ok"))
    monkeypatch.setattr(claude_cli_runner.subprocess, "run", rec)

    ex = _build_executor(rec)
    ex.run(prompt="p", system_instructions="", skill_markdown=None)

    cmd = rec.calls[0]["cmd"]
    sys_value = cmd[cmd.index("--system-prompt") + 1]
    assert "evaluating" in sys_value.lower()  # fallback wording


def test_run_uses_only_instructions_when_no_skill_markdown(monkeypatch) -> None:
    rec = _Recorder(stdout=_ok_payload("ok"))
    monkeypatch.setattr(claude_cli_runner.subprocess, "run", rec)

    ex = _build_executor(rec)
    ex.run(prompt="p", system_instructions="just-instructions", skill_markdown=None)

    cmd = rec.calls[0]["cmd"]
    sys_value = cmd[cmd.index("--system-prompt") + 1]
    assert sys_value == "just-instructions"


# ---- usage flow + cache warning -------------------------------------------


def test_warns_when_no_cache_activity(monkeypatch, caplog) -> None:
    rec = _Recorder(stdout=_ok_payload("ok"))  # cache_read=0, cache_creation=0
    monkeypatch.setattr(claude_cli_runner.subprocess, "run", rec)

    ex = _build_executor(rec)
    with caplog.at_level("WARNING"):
        ex.run(prompt="p", system_instructions="i", skill_markdown="tiny")
    assert any("cache" in r.message.lower() for r in caplog.records)


def test_no_warn_when_cache_creation_present(monkeypatch, caplog) -> None:
    rec = _Recorder(stdout=_ok_payload("ok", cache_creation_input_tokens=4096))
    monkeypatch.setattr(claude_cli_runner.subprocess, "run", rec)

    ex = _build_executor(rec)
    with caplog.at_level("WARNING"):
        ex.run(prompt="p", system_instructions="i", skill_markdown="big")
    assert not any("cache" in r.message.lower() for r in caplog.records)


# ---- error propagation ----------------------------------------------------


def test_cli_error_bubbles_up_to_caller(monkeypatch) -> None:
    rec = _Recorder(stdout="not json")
    monkeypatch.setattr(claude_cli_runner.subprocess, "run", rec)

    ex = _build_executor(rec)
    with pytest.raises(ClaudeCliError):
        ex.run(prompt="p", system_instructions="i", skill_markdown=None)


# ---- registry self-registration -------------------------------------------


def test_claude_cli_executor_self_registers() -> None:
    from scripts.eval.executors import EXECUTOR_REGISTRY

    assert "claude_cli" in EXECUTOR_REGISTRY
