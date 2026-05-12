"""Executor plugin boundary: ABC, ExecutionResult, and a string-ID registry.

`mock` and `claude_cli` are auto-imported below so they self-register with the
runtime registry. New executors should follow the same `register_executor(...)`
side-effect import pattern.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from scripts.eval.errors import UnknownExecutorError
from scripts.eval.usage import UsageSnapshot

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    output: str
    usage: UsageSnapshot | None = None
    raw_response: dict[str, Any] | None = None


class Executor(ABC):
    """Abstract executor contract.

    Implementations receive the rendered prompt + a (possibly empty) system instruction
    string + an optional SKILL.md body and return an ExecutionResult. The `expected`
    keyword exists so the MockExecutor can echo a task's expected value without coupling
    the orchestrator to the executor implementation; the CLI executor ignores it.
    """

    @abstractmethod
    def run(
        self,
        prompt: str,
        system_instructions: str,
        skill_markdown: str | None,
        *,
        expected: Any | None = None,
    ) -> ExecutionResult: ...


EXECUTOR_REGISTRY: dict[str, type[Executor]] = {}


def register_executor(name: str, cls: type[Executor]) -> None:
    if name in EXECUTOR_REGISTRY and EXECUTOR_REGISTRY[name] is not cls:
        logger.warning(
            "executor name %r already registered as %s; overwriting with %s",
            name,
            EXECUTOR_REGISTRY[name].__name__,
            cls.__name__,
        )
    EXECUTOR_REGISTRY[name] = cls


def get_executor(name: str, model: str) -> Executor:
    cls = EXECUTOR_REGISTRY.get(name)
    if cls is None:
        known = ", ".join(sorted(EXECUTOR_REGISTRY)) or "(none)"
        raise UnknownExecutorError(f"unknown executor '{name}' (known: {known})")
    return cls(model=model)


# Side-effect imports: each executor module registers itself on import.
from scripts.eval.executors import claude_cli as _claude_cli  # noqa: E402, F401
from scripts.eval.executors import mock as _mock  # noqa: E402, F401
