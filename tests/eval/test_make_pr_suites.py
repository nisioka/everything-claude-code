"""Task 8.4: run all 3 make-pr eval suites under the mock executor and assert pass."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval.cli import main


REPO_ROOT = Path(__file__).resolve().parents[2]
SUITES = [
    "evals/make-pr-commit-message/eval.yaml",
    "evals/make-pr-ticket-extract/eval.yaml",
    "evals/make-pr-sensitive-file/eval.yaml",
]


@pytest.mark.parametrize("rel_path", SUITES)
def test_suite_runs_under_mock_with_exit_zero(rel_path: str, tmp_path: Path) -> None:
    eval_yaml = REPO_ROOT / rel_path
    assert eval_yaml.exists(), f"missing eval suite: {eval_yaml}"

    out_json = tmp_path / "results.json"
    rc = main([str(eval_yaml), "--executor", "mock", "--output", str(out_json)])
    assert rc == 0, f"{rel_path} should exit 0 under mock"

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["error_count"] == 0
    assert payload["summary"]["fail_count"] == 0
    assert payload["summary"]["pass_count"] >= 3, "each suite must contain >= 3 tasks"
