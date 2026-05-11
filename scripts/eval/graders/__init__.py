"""Grader plugin boundary: ABC, registry, GraderResult, and aggregation helpers.

LlmJudgeGrader is added in task 7 with the same self-registering pattern as the
deterministic graders below.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from scripts.eval.errors import UnknownGraderError


# ---- Schema ---------------------------------------------------------------


class GraderResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    grader_name: str
    score: float  # 0.0..1.0
    passed: bool
    reason: str


# ---- ABC + registry -------------------------------------------------------


class Grader(ABC):
    @abstractmethod
    def grade(self, output: str, expected: Any, context: dict[str, Any]) -> GraderResult: ...


GRADER_REGISTRY: dict[str, type[Grader]] = {}


def register_grader(name: str, cls: type[Grader]) -> None:
    GRADER_REGISTRY[name] = cls


def get_grader(name: str) -> type[Grader]:
    cls = GRADER_REGISTRY.get(name)
    if cls is None:
        known = ", ".join(sorted(GRADER_REGISTRY)) or "(none)"
        raise UnknownGraderError(f"unknown grader '{name}' (known: {known})")
    return cls


def build_grader(name: str, grader_type: str, config: dict[str, Any]) -> Grader:
    """Instantiate a grader from its registered type + config dict.

    The grader class is responsible for validating its own config keys (mode etc.).
    """
    cls = get_grader(grader_type)
    return cls(name=name, config=config)


# ---- Aggregation helpers --------------------------------------------------

# A reason starting with one of these markers indicates the grader itself failed
# (network / config error), not that the model output was bad. The orchestrator
# uses this to mark the task as `error` rather than `fail` (Requirement 3.7).
_ERROR_MARKERS = ("GRADER_ERROR", "JUDGE_ERROR")

# Default pass threshold (Requirement 3.5). Graders may apply their own per-result
# threshold via GraderResult.passed; this threshold only governs the task-level
# weighted_score → status decision.
DEFAULT_PASS_THRESHOLD = 0.5


def aggregate(results: list[GraderResult], weights: list[float]) -> float:
    """Compute weighted average of grader scores; returns 0.0 for empty input."""
    if not results or sum(weights) == 0:
        return 0.0
    total = sum(r.score * w for r, w in zip(results, weights, strict=True))
    return total / sum(weights)


def summarise_status(
    results: list[GraderResult],
    weights: list[float],
    threshold: float = DEFAULT_PASS_THRESHOLD,
) -> str:
    """Decide task status: 'error' if any grader errored, else pass/fail by score."""
    for r in results:
        if any(r.reason.startswith(marker) for marker in _ERROR_MARKERS):
            return "error"
    score = aggregate(results, weights)
    return "pass" if score >= threshold else "fail"


# Side-effect imports: each grader module registers itself on import.
from scripts.eval.graders import list_match as _list_match  # noqa: E402, F401
from scripts.eval.graders import llm_judge as _llm_judge  # noqa: E402, F401
from scripts.eval.graders import regex as _regex  # noqa: E402, F401
