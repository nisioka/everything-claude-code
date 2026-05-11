"""Tests for LlmJudgeGrader (task 7.2).

Mocks the Anthropic SDK so no network calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from anthropic import APIStatusError

from scripts.eval.graders import GraderResult
from scripts.eval.graders.llm_judge import LlmJudgeGrader


def _resp(status: int) -> httpx.Response:
    req = httpx.Request("POST", "https://example.test/v1/messages")
    return httpx.Response(status_code=status, request=req)


def _judge_response(json_text: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json_text)],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
    )


class _FakeMessages:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeAnthropic:
    def __init__(self, responses) -> None:
        self.messages = _FakeMessages(responses)


def _make_grader(responses, **config_overrides):
    fake = _FakeAnthropic(responses)
    config = {
        "rubric": "Subject is concise and imperative.",
        "judge_model": "claude-sonnet-4-6",
        **config_overrides,
    }
    return LlmJudgeGrader(name="judge", config=config, client=fake), fake


# ---- Happy path ----------------------------------------------------------


def test_judge_returns_score_and_reason() -> None:
    g, _ = _make_grader([_judge_response('{"score": 0.85, "reason": "Good imperative subject"}')])
    res = g.grade("feat: add x", expected=None, context={})
    assert isinstance(res, GraderResult)
    assert res.score == pytest.approx(0.85)
    assert res.passed is True  # default threshold 0.5
    assert "imperative" in res.reason.lower()


def test_judge_low_score_fails() -> None:
    g, _ = _make_grader([_judge_response('{"score": 0.2, "reason": "Too verbose"}')])
    res = g.grade("very long output", expected=None, context={})
    assert res.passed is False


def test_judge_extracts_json_from_surrounding_prose() -> None:
    """Models often wrap JSON in prose / fences — the grader should extract it."""
    payload = 'Sure — here is my eval:\n```json\n{"score": 1.0, "reason": "ok"}\n```'
    g, _ = _make_grader([_judge_response(payload)])
    res = g.grade("anything", expected=None, context={})
    assert res.passed is True


def test_judge_passes_rubric_in_prompt() -> None:
    g, fake = _make_grader([_judge_response('{"score": 1, "reason": "ok"}')])
    g.grade("output", expected="expected", context={})
    call = fake.messages.calls[0]
    user_content = call["messages"][0]["content"]
    assert "Subject is concise" in user_content
    assert "output" in user_content
    assert "expected" in user_content


# ---- Validation errors ---------------------------------------------------


def test_judge_score_out_of_range_is_error() -> None:
    g, _ = _make_grader([_judge_response('{"score": 1.5, "reason": "wat"}')])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


def test_judge_missing_reason_is_error() -> None:
    g, _ = _make_grader([_judge_response('{"score": 0.7}')])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


def test_judge_invalid_json_is_error() -> None:
    g, _ = _make_grader([_judge_response("not json at all")])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


# ---- API failure ---------------------------------------------------------


def test_judge_api_5xx_returns_error_result(monkeypatch) -> None:
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda *_: None)
    g, _ = _make_grader(
        [APIStatusError("boom", response=_resp(500), body=None)] * 3
    )
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


def test_judge_api_4xx_returns_error_result(monkeypatch) -> None:
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda *_: None)
    g, _ = _make_grader([APIStatusError("auth", response=_resp(401), body=None)])
    res = g.grade("output", expected=None, context={})
    assert res.passed is False
    assert "JUDGE_ERROR" in res.reason


# ---- Registry self-registration -----------------------------------------


def test_llm_judge_self_registers() -> None:
    from scripts.eval.graders import GRADER_REGISTRY

    assert "llm_judge" in GRADER_REGISTRY


# ---- Orchestrator integration: judge error → task error -----------------


def test_orchestrator_marks_task_error_on_judge_failure(tmp_path, monkeypatch) -> None:
    """E2E-ish: a failing judge under a non-mock executor must produce status 'error'."""
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda *_: None)
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

    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: anthropic}
            tasks:
              - id: t1
                prompt: p
                expected: "feat: add x"
            graders:
              - type: llm_judge
                name: judge
                config:
                  rubric: "anything"
                  judge_model: "claude-sonnet-4-6"
            """
        ).strip(),
        encoding="utf-8",
    )

    fake = _FakeAnthropic([APIStatusError("boom", response=_resp(500), body=None)] * 3)

    # Patch the LlmJudgeGrader to use our fake client by monkeypatching its constructor.
    original_init = LlmJudgeGrader.__init__

    def patched_init(self, name, config, client=None, retry_handler=None):
        original_init(self, name=name, config=config, client=fake, retry_handler=None)

    monkeypatch.setattr(LlmJudgeGrader, "__init__", patched_init)

    cfg = ConfigLoader().load(p)
    res = Orchestrator().run(cfg, p)
    assert res.task_results[0].status == "error"
