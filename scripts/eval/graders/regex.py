"""RegexGrader — deterministic match / no_match scoring with optional re flags."""

from __future__ import annotations

import re
from functools import reduce
from operator import or_
from typing import Any

from scripts.eval.graders import GraderResult, register_grader
from scripts.eval.graders import Grader

_VALID_MODES = {"match", "no_match"}


class RegexGrader(Grader):
    """Score 1.0 when the regex matches (mode=match) or doesn't (mode=no_match)."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.pattern = config.get("pattern", "")
        self.mode = config.get("mode", "match")
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"RegexGrader '{name}': invalid mode '{self.mode}' "
                f"(expected one of {sorted(_VALID_MODES)})"
            )
        self.flags = self._parse_flags(config.get("flags", []))

    @staticmethod
    def _parse_flags(flag_specs: list[str] | int) -> int:
        if isinstance(flag_specs, int):
            return flag_specs
        if not flag_specs:
            return 0
        bits: list[int] = []
        for spec in flag_specs:
            attr = getattr(re, spec, None)
            if not isinstance(attr, int) and not isinstance(attr, re.RegexFlag):
                raise ValueError(f"unknown re flag: {spec}")
            bits.append(int(attr))
        return reduce(or_, bits, 0)

    def grade(self, output: str, expected: Any, context: dict[str, Any]) -> GraderResult:
        try:
            matched = re.search(self.pattern, output, self.flags) is not None
        except re.error as e:
            return GraderResult(
                grader_name=self.name,
                score=0.0,
                passed=False,
                reason=f"GRADER_ERROR: invalid regex {self.pattern!r}: {e}",
            )

        if self.mode == "match":
            passed = matched
            reason = f"Pattern {'matched' if matched else 'did not match'} {self.pattern!r}"
        else:  # no_match
            passed = not matched
            reason = (
                f"Pattern {self.pattern!r} {'absent (expected)' if not matched else 'unexpectedly matched'}"
            )

        return GraderResult(
            grader_name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            reason=reason,
        )


register_grader("regex", RegexGrader)
