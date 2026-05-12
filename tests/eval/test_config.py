"""Tests for the YAML schema and ConfigLoader (task 2.3).

Covers:
- Schema validation (Pydantic models, frozen=True, Literal constraints)
- YAML loader normal path (3 grader types, multi-task, fixture interpolation)
- Error path (missing required fields, unknown executor, broken YAML, missing fixture)
- Idempotency of repeated loads
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.eval.config import ConfigLoader, EvalConfig, GraderConfig, RunnerConfig, TaskConfig
from scripts.eval.errors import ConfigValidationError


# ---- Pydantic schema -------------------------------------------------------


def test_runner_config_defaults() -> None:
    cfg = RunnerConfig()
    assert cfg.executor == "mock"
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.skill_path is None
    assert cfg.instructions == ""


def test_runner_config_rejects_unknown_executor() -> None:
    with pytest.raises(Exception):
        RunnerConfig(executor="copilot")  # type: ignore[arg-type]


def test_grader_config_rejects_unknown_type() -> None:
    with pytest.raises(Exception):
        GraderConfig(type="foo", name="x", config={})  # type: ignore[arg-type]


def test_models_are_frozen() -> None:
    cfg = RunnerConfig()
    with pytest.raises(Exception):
        cfg.executor = "claude_cli"  # type: ignore[misc]


def test_task_config_minimal() -> None:
    t = TaskConfig(id="t1", prompt="hello")
    assert t.id == "t1"
    assert t.prompt == "hello"
    assert t.expected is None
    assert t.fixtures == {}


# ---- ConfigLoader normal path ---------------------------------------------


@pytest.fixture()
def yaml_dir(tmp_path: Path) -> Path:
    """Create a directory with an eval.yaml + fixtures for happy-path tests."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "diff.txt").write_text("diff --git a/x b/x\n+hello\n", encoding="utf-8")

    eval_yaml = tmp_path / "eval.yaml"
    eval_yaml.write_text(
        dedent(
            """
            config:
              executor: mock
              model: claude-sonnet-4-6
              instructions: "Generate a commit message."

            tasks:
              - id: t-feat
                prompt: |
                  Diff:
                  {{diff}}
                fixtures:
                  diff: fixtures/diff.txt
                expected: "feat: add hello"
              - id: t-fix
                prompt: "Plain prompt without fixture"
                expected: "fix"

            graders:
              - type: regex
                name: conv_type
                weight: 2.0
                config:
                  pattern: "^(feat|fix):"
                  mode: match
              - type: list_match
                name: items
                weight: 1.0
                config:
                  expected_items: ["a", "b"]
                  mode: superset
              - type: llm_judge
                name: subject
                weight: 1.5
                config:
                  judge_model: claude-sonnet-4-6
                  rubric: "Subject is concise."
            """
        ).strip(),
        encoding="utf-8",
    )
    return tmp_path


def test_loader_returns_eval_config(yaml_dir: Path) -> None:
    cfg = ConfigLoader().load(yaml_dir / "eval.yaml")
    assert isinstance(cfg, EvalConfig)
    assert cfg.config.executor == "mock"
    assert len(cfg.tasks) == 2
    assert len(cfg.graders) == 3
    assert {g.type for g in cfg.graders} == {"regex", "list_match", "llm_judge"}


def test_loader_resolves_fixture_relative_to_yaml(yaml_dir: Path) -> None:
    cfg = ConfigLoader().load(yaml_dir / "eval.yaml")
    feat = cfg.tasks[0]
    assert "diff --git a/x b/x" in feat.prompt
    assert "{{diff}}" not in feat.prompt


def test_loader_leaves_prompt_alone_without_fixture(yaml_dir: Path) -> None:
    cfg = ConfigLoader().load(yaml_dir / "eval.yaml")
    fix = cfg.tasks[1]
    assert fix.prompt == "Plain prompt without fixture"


def test_loader_is_idempotent(yaml_dir: Path) -> None:
    loader = ConfigLoader()
    a = loader.load(yaml_dir / "eval.yaml")
    b = loader.load(yaml_dir / "eval.yaml")
    assert a == b


# ---- ConfigLoader error path ----------------------------------------------


def test_missing_required_field_raises(tmp_path: Path) -> None:
    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config:
              executor: mock
            tasks: []
            # graders missing
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError) as exc:
        ConfigLoader().load(p)
    assert "graders" in str(exc.value)


def test_unknown_executor_raises(tmp_path: Path) -> None:
    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config:
              executor: copilot-sdk
            tasks:
              - id: t1
                prompt: hi
            graders:
              - type: regex
                name: r
                config: {pattern: ".*", mode: match}
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError):
        ConfigLoader().load(p)


def test_broken_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "eval.yaml"
    p.write_text("config: {executor: mock\n  bad indent: yes", encoding="utf-8")
    with pytest.raises(ConfigValidationError):
        ConfigLoader().load(p)


def test_missing_fixture_raises(tmp_path: Path) -> None:
    p = tmp_path / "eval.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: mock}
            tasks:
              - id: t1
                prompt: "{{diff}}"
                fixtures: {diff: fixtures/missing.txt}
            graders:
              - type: regex
                name: r
                config: {pattern: ".*", mode: match}
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError) as exc:
        ConfigLoader().load(p)
    assert "missing.txt" in str(exc.value)


def test_missing_yaml_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError):
        ConfigLoader().load(tmp_path / "does-not-exist.yaml")


def test_fixture_path_traversal_is_rejected(tmp_path: Path) -> None:
    """Security regression: fixture paths must stay within the eval.yaml directory."""
    eval_dir = tmp_path / "evals"
    eval_dir.mkdir()
    # Plant a "secret" outside the eval dir to confirm it cannot be read.
    secret = tmp_path / "secret.txt"
    secret.write_text("sk-ant-totally-secret", encoding="utf-8")

    p = eval_dir / "eval.yaml"
    p.write_text(
        dedent(
            """
            config: {executor: mock}
            tasks:
              - id: t1
                prompt: "{{leak}}"
                fixtures: {leak: ../secret.txt}
            graders:
              - type: regex
                name: r
                config: {pattern: ".*", mode: match}
            """
        ).strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError) as exc:
        ConfigLoader().load(p)
    assert "escape" in str(exc.value).lower()
