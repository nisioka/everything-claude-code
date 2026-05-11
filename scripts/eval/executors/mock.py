"""MockExecutor — returns task.expected as-is so graders/runner can be exercised offline."""

from __future__ import annotations

import json
from typing import Any

from scripts.eval.executors import ExecutionResult, Executor, register_executor


class MockExecutor(Executor):
    """No-op executor: echoes the task's `expected` value as the model output.

    Output formatting (chosen to match the natural shape the real model would emit so
    the same grader config works for both mock and anthropic runs):
    - str  → returned verbatim
    - list → joined with newlines (one item per line) — what list_match `parse_mode=lines` expects
    - other (dict, etc.) → JSON-serialised
    - None → empty string
    `usage` is always None since no API call is made.
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
        elif isinstance(expected, list):
            output = "\n".join(str(item) for item in expected)
        else:
            output = json.dumps(expected, ensure_ascii=False)
        return ExecutionResult(output=output, usage=None)


register_executor("mock", MockExecutor)
