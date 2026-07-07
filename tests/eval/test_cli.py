"""Tests for CLI entry point (task 5.3 + 5.4 — integration via main())."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.eval.cli import main


def _write_pass_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "pass.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: mock}
            tasks:
              - id: t1
                prompt: p
                expected: "feat: hi"
            graders:
              - type: regex
                name: r
                config: {pattern: "^feat:", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    return p


def _write_fail_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "fail.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: mock}
            tasks:
              - id: t1
                prompt: p
                expected: "broken"
            graders:
              - type: regex
                name: r
                config: {pattern: "^feat:", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    return p


def test_cli_no_args_returns_zero(capsys) -> None:
    assert main([]) == 0


def test_cli_pass_returns_zero(tmp_path: Path) -> None:
    p = _write_pass_yaml(tmp_path)
    assert main([str(p)]) == 0


def test_cli_fail_returns_one(tmp_path: Path) -> None:
    p = _write_fail_yaml(tmp_path)
    assert main([str(p)]) == 1


def test_cli_invalid_yaml_returns_two(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("not: a: valid mapping: structure", encoding="utf-8")
    assert main([str(p)]) == 2


def test_cli_missing_file_returns_two(tmp_path: Path) -> None:
    assert main([str(tmp_path / "no-such.yaml")]) == 2


def test_cli_writes_output_json(tmp_path: Path) -> None:
    p = _write_pass_yaml(tmp_path)
    out = tmp_path / "out.json"
    rc = main([str(p), "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["task_results"][0]["task_id"] == "t1"


def test_cli_executor_override(tmp_path: Path) -> None:
    """Override claude_cli→mock so the test never spawns a subprocess."""
    p = tmp_path / "claude_cli.yaml"
    p.write_text(
        dedent(
            """
            config:
              executor: claude_cli
              model: claude-sonnet-5
            tasks:
              - id: t1
                prompt: p
                expected: "feat: ok"
            graders:
              - type: regex
                name: r
                config: {pattern: "^feat:", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    rc = main([str(p), "--executor", "mock"])
    assert rc == 0


def test_cli_verbose_does_not_crash(tmp_path: Path, capsys) -> None:
    p = _write_pass_yaml(tmp_path)
    rc = main([str(p), "--verbose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "t1" in out
