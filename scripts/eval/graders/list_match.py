"""ListMatchGrader — exact / superset / subset comparison after parsing output as a list."""

from __future__ import annotations

import json
from typing import Any

from scripts.eval.graders import GraderResult, register_grader
from scripts.eval.graders import Grader

_VALID_MODES = {"exact", "superset", "subset"}
_VALID_PARSE_MODES = {"lines", "json_array"}


class ListMatchGrader(Grader):
    """Compare a list of expected items against a list parsed from the model output."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.expected_items = [str(x) for x in config.get("expected_items", [])]
        self.mode = config.get("mode", "exact")
        self.parse_mode = config.get("parse_mode", "lines")
        # When True, the per-task `expected` field (a list) overrides config.expected_items.
        # Use this when one eval.yaml mixes positive (must-detect) and negative (clean) tasks.
        self.use_task_expected = bool(config.get("use_task_expected", False))

        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"ListMatchGrader '{name}': invalid mode '{self.mode}' "
                f"(expected one of {sorted(_VALID_MODES)})"
            )
        if self.parse_mode not in _VALID_PARSE_MODES:
            raise ValueError(
                f"ListMatchGrader '{name}': invalid parse_mode '{self.parse_mode}' "
                f"(expected one of {sorted(_VALID_PARSE_MODES)})"
            )

    def grade(self, output: str, expected: Any, context: dict[str, Any]) -> GraderResult:
        try:
            actual = self._parse(output)
        except (json.JSONDecodeError, ValueError) as e:
            return GraderResult(
                grader_name=self.name,
                score=0.0,
                passed=False,
                reason=f"GRADER_ERROR: failed to parse output as {self.parse_mode}: {e}",
            )

        if self.use_task_expected:
            if not isinstance(expected, list):
                return GraderResult(
                    grader_name=self.name,
                    score=0.0,
                    passed=False,
                    reason=(
                        f"GRADER_ERROR: use_task_expected=True but task.expected is "
                        f"{type(expected).__name__}, not list"
                    ),
                )
            expected_items = [str(x) for x in expected]
        else:
            expected_items = self.expected_items

        actual_set = set(actual)
        expected_set = set(expected_items)

        if self.mode == "exact":
            passed = actual_set == expected_set
            reason = f"exact: actual={sorted(actual_set)} expected={sorted(expected_set)}"
        elif self.mode == "superset":
            passed = expected_set.issubset(actual_set)
            missing = expected_set - actual_set
            reason = (
                f"superset: actual ⊇ expected: ok"
                if passed
                else f"superset: missing {sorted(missing)}"
            )
        else:  # subset
            passed = actual_set.issubset(expected_set)
            extra = actual_set - expected_set
            reason = (
                f"subset: actual ⊆ expected: ok"
                if passed
                else f"subset: unexpected items {sorted(extra)}"
            )

        return GraderResult(
            grader_name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            reason=reason,
        )

    def _parse(self, output: str) -> list[str]:
        if self.parse_mode == "lines":
            return [line.strip() for line in output.splitlines() if line.strip()]
        # json_array
        data = json.loads(output)
        if not isinstance(data, list):
            raise ValueError(f"expected JSON array, got {type(data).__name__}")
        return [str(x) for x in data]


register_grader("list_match", ListMatchGrader)
