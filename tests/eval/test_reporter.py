"""Tests for Reporter — terminal summary + JSON output (task 5.2)."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.eval.config import ConfigLoader
from scripts.eval.orchestrator import Orchestrator
from scripts.eval.reporter import Reporter


@pytest.fixture()
def simple_result(tmp_path: Path):
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
                name: r
                config: {pattern: "^feat:", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = ConfigLoader().load(p)
    return Orchestrator().run(cfg, p), p


def test_reporter_summary_includes_counts(simple_result, capsys) -> None:
    result, _ = simple_result
    Reporter().print_summary(result, verbose=False)
    captured = capsys.readouterr()
    assert "pass" in captured.out.lower()
    assert "1" in captured.out  # 1 task pass
    assert "weighted" in captured.out.lower() or "score" in captured.out.lower()


def test_reporter_verbose_prints_grader_breakdown(simple_result, capsys) -> None:
    result, _ = simple_result
    Reporter().print_summary(result, verbose=True)
    captured = capsys.readouterr()
    assert "t1" in captured.out
    assert "r" in captured.out  # grader name appears


def test_reporter_writes_json(simple_result, tmp_path: Path) -> None:
    result, _ = simple_result
    out = tmp_path / "results.json"
    Reporter().write_json(result, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["task_results"][0]["task_id"] == "t1"
    assert "summary" in payload
    assert payload["summary"]["pass_count"] == 1
