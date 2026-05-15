"""MockExecutor — returns task.expected as-is so graders/runner can be exercised offline."""

from __future__ import annotations

import json
import os
from typing import Any

from scripts.eval.executors import ExecutionResult, Executor, register_executor

_MOCK_FORMAT_ENV = "EVAL_HARNESS_MOCK_FORMAT"
_VALID_FORMATS = {"lines", "json"}


class MockExecutor(Executor):
    """No-op executor: echoes the task's `expected` value as the model output.

    Output formatting for non-string `expected` is selected by the
    `EVAL_HARNESS_MOCK_FORMAT` env var:
    - `lines` (default) — list items joined with `\\n`, dicts JSON-encoded.
      Matches `list_match parse_mode=lines`, which is the default.
    - `json` — every non-string is `json.dumps`-encoded. Use this when a suite has
      a `list_match parse_mode=json_array` grader.

    String `expected` is always returned verbatim and `None` produces an empty string.
    `usage` is always None since no API call is made.
    """

    def __init__(self, model: str = "mock") -> None:
        self.model = model
        fmt = os.environ.get(_MOCK_FORMAT_ENV, "lines")
        if fmt not in _VALID_FORMATS:
            raise ValueError(
                f"{_MOCK_FORMAT_ENV}={fmt!r} is invalid; expected one of {sorted(_VALID_FORMATS)}"
            )
        self.output_format = fmt

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
        elif self.output_format == "json":
            output = json.dumps(expected, ensure_ascii=False)
        elif isinstance(expected, list):
            output = "\n".join(str(item) for item in expected)
        else:
            output = json.dumps(expected, ensure_ascii=False)
        return ExecutionResult(output=output, usage=None)


register_executor("mock", MockExecutor)
