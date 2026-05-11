"""Tests for CI comment-builder + exit-aggregator (task 9.2 + 9.3)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from scripts.eval.ci import aggregate_exit, build_comment


def _result(pass_count: int, fail_count: int, error_count: int, total: int = None):
    total = total if total is not None else pass_count + fail_count + error_count
    return {
        "eval_path": "evals/x/eval.yaml",
        "task_results": [],
        "summary": {
            "total_tasks": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "error_count": error_count,
            "weighted_average": 1.0 if pass_count == total else 0.5,
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cache_read_tokens": 4096,
            "total_cache_creation_tokens": 0,
            "cache_hit_ratio": 1.0,
            "elapsed_ms": 1234,
        },
    }


def _write(dir_: Path, name: str, payload: dict) -> None:
    (dir_ / name).write_text(json.dumps(payload), encoding="utf-8")


# ---- build_comment --------------------------------------------------------


def test_build_comment_includes_marker_and_table(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "make-pr-commit-message.json", _result(3, 0, 0))
    _write(tmp_path, "make-pr-ticket-extract.json", _result(2, 1, 0))
    rc = build_comment.main(["build_comment.py", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "<!-- eval-make-pr-comment -->" in captured
    assert "make-pr-commit-message" in captured
    assert "make-pr-ticket-extract" in captured
    assert "✅" in captured  # passing suite
    assert "❌" in captured  # failing suite


def test_build_comment_handles_empty_dir(tmp_path: Path, capsys) -> None:
    rc = build_comment.main(["build_comment.py", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no results" in out


def test_build_comment_handles_corrupt_json(tmp_path: Path, capsys) -> None:
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    rc = build_comment.main(["build_comment.py", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "parse-error" in out


# ---- aggregate_exit -------------------------------------------------------


def test_aggregate_exit_all_pass(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "a.json", _result(3, 0, 0))
    _write(tmp_path, "b.json", _result(2, 0, 0))
    rc = aggregate_exit.main(["aggregate_exit.py", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "0"


def test_aggregate_exit_with_fail(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "a.json", _result(3, 0, 0))
    _write(tmp_path, "b.json", _result(2, 1, 0))
    rc = aggregate_exit.main(["aggregate_exit.py", str(tmp_path)])
    assert rc == 1
    assert capsys.readouterr().out.strip() == "1"


def test_aggregate_exit_error_takes_precedence(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "a.json", _result(2, 1, 0))
    _write(tmp_path, "b.json", _result(2, 0, 1))
    rc = aggregate_exit.main(["aggregate_exit.py", str(tmp_path)])
    assert rc == 2
    assert capsys.readouterr().out.strip() == "2"


def test_aggregate_exit_corrupt_returns_2(tmp_path: Path, capsys) -> None:
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    rc = aggregate_exit.main(["aggregate_exit.py", str(tmp_path)])
    assert rc == 2
    assert capsys.readouterr().out.strip() == "2"


def test_aggregate_exit_missing_arg() -> None:
    rc = aggregate_exit.main(["aggregate_exit.py"])
    assert rc == 2
