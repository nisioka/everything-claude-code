"""Tests for Orchestrator (task 5.1).

Covers:
- Mock executor + grader pipeline returns expected TaskResult / EvalResult shape
- Per-task error isolation: a failing grader on task A doesn't kill task B
- weighted_score is computed correctly
- elapsed_ms is non-negative; usage is None for mock
- Single-task error returns status='error' on that task only
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.eval.config import ConfigLoader
from scripts.eval.orchestrator import EvalResult, Orchestrator, TaskResult


@pytest.fixture()
def mixed_eval_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config:
              executor: mock
            tasks:
              - id: pass-task
                prompt: "p"
                expected: "feat: add"
              - id: fail-task
                prompt: "p"
                expected: "broken-prefix"
            graders:
              - type: regex
                name: conv_type
                weight: 1.0
                config:
                  pattern: "^(feat|fix):"
                  mode: match
            """
        ).strip(),
        encoding="utf-8",
    )
    return p


def test_orchestrator_returns_eval_result(mixed_eval_yaml: Path) -> None:
    cfg = ConfigLoader().load(mixed_eval_yaml)
    res = Orchestrator().run(cfg, mixed_eval_yaml)
    assert isinstance(res, EvalResult)
    assert len(res.task_results) == 2
    statuses = {tr.task_id: tr.status for tr in res.task_results}
    assert statuses == {"pass-task": "pass", "fail-task": "fail"}


def test_orchestrator_summary_counts(mixed_eval_yaml: Path) -> None:
    cfg = ConfigLoader().load(mixed_eval_yaml)
    res = Orchestrator().run(cfg, mixed_eval_yaml)
    assert res.summary.total_tasks == 2
    assert res.summary.pass_count == 1
    assert res.summary.fail_count == 1
    assert res.summary.error_count == 0


def test_orchestrator_weighted_score(tmp_path: Path) -> None:
    """weighted_score should be 2/(2+1) when one of two graders fails."""
    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: mock}
            tasks:
              - id: t1
                prompt: p
                expected: "feat: add"
            graders:
              - type: regex
                name: r-pass
                weight: 2.0
                config: {pattern: "^feat:", mode: match}
              - type: regex
                name: r-fail
                weight: 1.0
                config: {pattern: "^docs:", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = ConfigLoader().load(p)
    res = Orchestrator().run(cfg, p)
    assert res.task_results[0].weighted_score == pytest.approx(2 / 3)
    # default threshold 0.5 → pass
    assert res.task_results[0].status == "pass"


def test_orchestrator_isolates_executor_failure(tmp_path: Path, monkeypatch) -> None:
    """An exception inside one task's executor must not abort sibling tasks."""
    from scripts.eval.executors import ExecutionResult, Executor

    class _Bomb(Executor):
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt, system_instructions, skill_markdown, *, expected=None):
            if expected == "boom":
                raise RuntimeError("explode")
            return ExecutionResult(output=str(expected or ""))

    monkeypatch.setattr(
        "scripts.eval.orchestrator.get_executor",
        lambda name, model: _Bomb(model=model),
    )
    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: mock}
            tasks:
              - id: ok
                prompt: p
                expected: "feat: add"
              - id: bad
                prompt: p
                expected: "boom"
            graders:
              - type: regex
                name: r
                weight: 1.0
                config: {pattern: "^feat:", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = ConfigLoader().load(p)
    res = Orchestrator().run(cfg, p)
    statuses = {tr.task_id: tr.status for tr in res.task_results}
    assert statuses == {"ok": "pass", "bad": "error"}
    bad = next(tr for tr in res.task_results if tr.task_id == "bad")
    assert "explode" in bad.error


def test_orchestrator_records_elapsed_ms(mixed_eval_yaml: Path) -> None:
    cfg = ConfigLoader().load(mixed_eval_yaml)
    res = Orchestrator().run(cfg, mixed_eval_yaml)
    for tr in res.task_results:
        assert tr.elapsed_ms >= 0


def test_task_result_serialises_cleanly(mixed_eval_yaml: Path) -> None:
    cfg = ConfigLoader().load(mixed_eval_yaml)
    res = Orchestrator().run(cfg, mixed_eval_yaml)
    dumped = res.model_dump()
    assert isinstance(dumped, dict)
    assert dumped["task_results"][0]["task_id"] == "pass-task"
    assert "summary" in dumped
