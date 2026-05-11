"""Tests for Executor ABC, registry, and MockExecutor (task 3.3).

Covers:
- Registry register / get round-trip
- get_executor with unknown name raises UnknownExecutorError
- ABC enforces run() signature on subclasses
- MockExecutor returns task-bound expected text and usage=None
- ExecutionResult fields
"""

from __future__ import annotations

import pytest

from scripts.eval.errors import UnknownExecutorError
from scripts.eval.executors import (
    EXECUTOR_REGISTRY,
    ExecutionResult,
    Executor,
    get_executor,
    register_executor,
)
from scripts.eval.executors.mock import MockExecutor


# ---- ExecutionResult schema ------------------------------------------------


def test_execution_result_minimal() -> None:
    r = ExecutionResult(output="hello")
    assert r.output == "hello"
    assert r.usage is None
    assert r.raw_response is None


# ---- Registry --------------------------------------------------------------


def test_register_and_get_executor() -> None:
    class _DummyExec(Executor):
        def __init__(self, model: str) -> None:
            self.model = model

        def run(
            self,
            prompt: str,
            system_instructions: str,
            skill_markdown: str | None,
            *,
            expected: object | None = None,
        ) -> ExecutionResult:
            return ExecutionResult(output="ok")

    register_executor("_dummy", _DummyExec)
    try:
        ex = get_executor("_dummy", model="m")
        assert isinstance(ex, _DummyExec)
        assert ex.model == "m"
    finally:
        EXECUTOR_REGISTRY.pop("_dummy", None)


def test_get_unknown_executor_raises() -> None:
    with pytest.raises(UnknownExecutorError) as exc:
        get_executor("does-not-exist", model="m")
    assert "does-not-exist" in str(exc.value)


def test_mock_executor_is_registered_on_import() -> None:
    """MockExecutor self-registers via executors/__init__.py side-effect import."""
    assert "mock" in EXECUTOR_REGISTRY
    ex = get_executor("mock", model="ignored")
    assert isinstance(ex, MockExecutor)


# ---- ABC enforcement ------------------------------------------------------


def test_abc_rejects_subclass_without_run() -> None:
    class _Broken(Executor):
        pass

    with pytest.raises(TypeError):
        _Broken()  # type: ignore[abstract]


# ---- MockExecutor ---------------------------------------------------------


def test_mock_executor_returns_expected_as_output() -> None:
    ex = MockExecutor(model="ignored")
    res = ex.run(
        prompt="anything",
        system_instructions="ignored",
        skill_markdown=None,
        expected="canned-output",
    )
    assert res.output == "canned-output"
    assert res.usage is None


def test_mock_executor_handles_missing_expected() -> None:
    """If expected is None we still return a deterministic empty string output."""
    ex = MockExecutor(model="ignored")
    res = ex.run(prompt="p", system_instructions="s", skill_markdown=None, expected=None)
    assert res.output == ""
    assert res.usage is None


def test_mock_executor_joins_list_with_newlines() -> None:
    """Lists are emitted one-per-line so list_match parse_mode='lines' works on mock."""
    ex = MockExecutor(model="ignored")
    res = ex.run(
        prompt="p", system_instructions="s", skill_markdown=None, expected=["a", "b"]
    )
    assert res.output == "a\nb"


def test_mock_executor_json_serializes_dict() -> None:
    ex = MockExecutor(model="ignored")
    res = ex.run(
        prompt="p", system_instructions="s", skill_markdown=None, expected={"k": "v"}
    )
    assert '"k"' in res.output and '"v"' in res.output
