"""Tests for LlmJudgeGrader — mocks the `claude -p` subprocess call."""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.eval import claude_cli_runner
from scripts.eval.errors import ClaudeCliError
from scripts.eval.graders import GraderResult
from scripts.eval.graders.llm_judge import LlmJudgeGrader


def _judge_payload(json_text: str) -> str:
    return json.dumps(
        {
            "is_error": False,
            "result": json_text,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }
    )


def _fake_completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class _Runner:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _ensure_claude_on_path(monkeypatch):
    monkeypatch.setattr(claude_cli_runner.shutil, "which", lambda _: "/usr/bin/claude")


def _make_grader(responses, **config_overrides):
    runner = _Runner(responses)
    config = {
        "rubric": "Subject is concise and imperative.",
        "judge_model": "claude-sonnet-5",
        **config_overrides,
    }
    return LlmJudgeGrader(name="judge", config=config, runner=runner), runner


# ---- happy path ----------------------------------------------------------


def test_judge_returns_score_and_reason() -> None:
    g, _ = _make_grader(
        [_fake_completed(stdout=_judge_payload('{"score": 0.85, "reason": "Good imperative subject"}'))]
    )
    res = g.grade("feat: add x", expected=None, context={})
    assert isinstance(res, GraderResult)
    assert res.score == pytest.approx(0.85)
    assert res.passed is True
    assert "imperative" in res.reason.lower()


def test_judge_low_score_fails() -> None:
    g, _ = _make_grader(
        [_fake_completed(stdout=_judge_payload('{"score": 0.2, "reason": "Too verbose"}'))]
    )
    res = g.grade("very long output", expected=None, context={})
    assert res.passed is False


def test_judge_extracts_json_from_surrounding_prose() -> None:
    payload = 'Sure — here is my eval:\n```json\n{"score": 1.0, "reason": "ok"}\n```'
    g, _ = _make_grader([_fake_completed(stdout=_judge_payload(payload))])
    res = g.grade("anything", expected=None, context={})
    assert res.passed is True


def test_judge_handles_trailing_brace_block_after_first_object() -> None:
    payload = (
        '{"score": 0.9, "reason": "ok"} '
        "and here is some debug info: {\"meta\": \"ignore-me\"}"
    )
    g, _ = _make_grader([_fake_completed(stdout=_judge_payload(payload))])
    res = g.grade("anything", expected=None, context={})
    assert res.score == pytest.approx(0.9)


def test_judge_skips_non_object_braces_before_real_json() -> None:
    payload = 'Note: avoid using {curly} braces.\n{"score": 0.7, "reason": "good"}'
    g, _ = _make_grader([_fake_completed(stdout=_judge_payload(payload))])
    res = g.grade("anything", expected=None, context={})
    assert res.score == pytest.approx(0.7)


def test_judge_passes_rubric_in_prompt() -> None:
    g, runner = _make_grader([_fake_completed(stdout=_judge_payload('{"score": 1, "reason": "ok"}'))])
    g.grade("output", expected="expected", context={})

    call = runner.calls[0]
    piped = call["kwargs"]["input"]
    assert "Subject is concise" in piped
    assert "output" in piped
    assert "expected" in piped


def test_judge_skips_under_mock_executor() -> None:
    g, runner = _make_grader([_fake_completed(stdout=_judge_payload('{"score": 1, "reason": "x"}'))])
    res = g.grade("anything", expected=None, context={"executor": "mock"})
    assert res.passed is True
    assert "MOCK_JUDGE_SKIPPED" in res.reason
    # no subprocess call made
    assert runner.calls == []


# ---- Validation errors ---------------------------------------------------


def test_judge_score_out_of_range_is_error() -> None:
    g, _ = _make_grader([_fake_completed(stdout=_judge_payload('{"score": 1.5, "reason": "wat"}'))])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


def test_judge_missing_reason_is_error() -> None:
    g, _ = _make_grader([_fake_completed(stdout=_judge_payload('{"score": 0.7}'))])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


def test_judge_invalid_json_in_result_is_error() -> None:
    g, _ = _make_grader([_fake_completed(stdout=_judge_payload("not json at all"))])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


# ---- CLI failure --------------------------------------------------------


def test_judge_cli_failure_returns_error_result() -> None:
    g, _ = _make_grader([_fake_completed(stdout="not json", returncode=1)])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


def test_judge_timeout_returns_error_result() -> None:
    g, _ = _make_grader([subprocess.TimeoutExpired(cmd="claude", timeout=1)])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason
    assert "timed out" in res.reason


# ---- Registry self-registration -----------------------------------------


def test_llm_judge_self_registers() -> None:
    from scripts.eval.graders import GRADER_REGISTRY

    assert "llm_judge" in GRADER_REGISTRY


# ---- Orchestrator integration: judge error → task error -----------------


def test_orchestrator_marks_task_error_on_judge_failure(tmp_path, monkeypatch) -> None:
    """E2E-ish: a failing judge under a non-mock executor must produce status 'error'."""
    from textwrap import dedent

    from scripts.eval.config import ConfigLoader
    from scripts.eval.executors import ExecutionResult, Executor
    from scripts.eval.orchestrator import Orchestrator

    class _Echo(Executor):
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt, system_instructions, skill_markdown, *, expected=None):
            return ExecutionResult(output=str(expected or ""))

    monkeypatch.setattr(
        "scripts.eval.orchestrator.get_executor",
        lambda name, model: _Echo(model=model),
    )

    # Force the judge's CLI call to always fail.
    def _always_fail(*a, **kw):
        raise ClaudeCliError("simulated CLI failure")

    monkeypatch.setattr(
        "scripts.eval.graders.llm_judge.run_claude_cli",
        _always_fail,
    )

    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: claude_cli}
            tasks:
              - id: t1
                prompt: p
                expected: "feat: add x"
            graders:
              - type: llm_judge
                name: judge
                config:
                  rubric: "anything"
                  judge_model: "claude-sonnet-5"
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = ConfigLoader().load(p)
    res = Orchestrator().run(cfg, p)
    assert res.task_results[0].status == "error"
