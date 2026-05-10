"""MockExecutor — returns task.expected as-is so graders/runner can be exercised offline."""

from __future__ import annotations

import json
from typing import Any

from scripts.eval.executors import EXECUTOR_REGISTRY, ExecutionResult, Executor, register_executor


class MockExecutor(Executor):
    """No-op executor: echoes the task's `expected` value as the model output.

    String expecteds are returned verbatim. Non-string expecteds (lists, dicts) are
    JSON-serialised so list-style graders can parse them. `usage` is always None
    since no API call is made.
    """

    def __init__(self, model: str = "mock") -> None:
        self.model = model

    def run(
        self,
        prompt: str,
        system_instructions: str,
        skill_markdown: str | None,
        *,
        expected: Any | None = None,
    ) -> ExecutionResult:
        if expected is None:
            output = ""
        elif isinstance(expected, str):
            output = expected
        else:
            output = json.dumps(expected, ensure_ascii=False)
        return ExecutionResult(output=output, usage=None)


register_executor("mock", MockExecutor)
