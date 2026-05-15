"""LlmJudgeGrader — rubric-based judge via `claude -p --output-format json`.

Failure modes (CLI error, malformed JSON, score out of range, empty reason) are
folded into a single `JUDGE_ERROR: ...` GraderResult so the Orchestrator promotes
the task to `error` without needing to know about judge-specific failures.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from scripts.eval.claude_cli_runner import DEFAULT_TIMEOUT_SEC, run_claude_cli
from scripts.eval.errors import ClaudeCliError
from scripts.eval.graders import Grader, GraderResult, register_grader

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"

_JUDGE_SYSTEM = (
    "You are an evaluation judge. Read the rubric, the model output, and the expected "
    "value, then return ONLY a JSON object with two keys: `score` (a float between 0.0 "
    "and 1.0) and `reason` (a short justification string). Do not include any prose "
    "outside the JSON object."
)


class LlmJudgeGrader(Grader):
    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self.name = name
        self.rubric = config.get("rubric", "")
        self.judge_model = config.get("judge_model", DEFAULT_JUDGE_MODEL)
        self.threshold = float(config.get("pass_threshold", 0.5))
        self.timeout_sec = int(config.get("timeout_sec", DEFAULT_TIMEOUT_SEC))
        # `runner` is the subprocess.run injection point used by run_claude_cli.
        # Production callers leave it None.
        self._runner = runner

    def grade(self, output: str, expected: Any, context: dict[str, Any]) -> GraderResult:
        # Skip the actual judge call under the mock executor: the run exercises
        # runner mechanics, not model quality. A clear "skipped" reason makes this
        # visible in reports without polluting the pass count.
        if context.get("executor") == "mock":
            return GraderResult(
                grader_name=self.name,
                score=1.0,
                passed=True,
                reason="MOCK_JUDGE_SKIPPED: executor=mock, judge call bypassed",
            )

        prompt = self._build_prompt(output, expected)
        try:
            cli_result = run_claude_cli(
                prompt=prompt,
                system_prompt=_JUDGE_SYSTEM,
                model=self.judge_model,
                timeout_sec=self.timeout_sec,
                runner=self._runner,
            )
        except ClaudeCliError as e:
            return self._error(f"judge CLI call failed: {e}")

        raw = cli_result.text
        try:
            data = self._parse_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            return self._error(f"could not parse judge response as JSON: {e}; raw={raw[:200]!r}")

        try:
            score = float(data["score"])
            reason = data["reason"]
        except (KeyError, TypeError, ValueError) as e:
            return self._error(f"judge JSON missing required keys: {e}; raw={raw[:200]!r}")

        if not isinstance(reason, str) or not reason.strip():
            return self._error(f"judge JSON `reason` is empty or non-string; raw={raw[:200]!r}")
        if not 0.0 <= score <= 1.0:
            return self._error(f"judge JSON `score` out of range (0..1): {score}")

        return GraderResult(
            grader_name=self.name,
            score=score,
            passed=score >= self.threshold,
            reason=reason,
        )

    # ---- helpers ---------------------------------------------------------

    def _build_prompt(self, output: str, expected: Any) -> str:
        if expected is None:
            expected_repr = ""
        elif isinstance(expected, str):
            expected_repr = expected
        else:
            expected_repr = json.dumps(expected, ensure_ascii=False)
        return (
            f"Rubric:\n{self.rubric}\n\n"
            f"Expected (may be empty):\n{expected_repr}\n\n"
            f"Model output:\n{output}\n\n"
            f"Return JSON: {{\"score\": <float 0..1>, \"reason\": <string>}}"
        )

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extract the first JSON object from the response.

        Tolerates code fences, leading/trailing prose, and trailing junk after the
        object. Uses `JSONDecoder.raw_decode` rather than a greedy `\\{.*\\}` regex
        because the latter spans multiple objects and falsely reports `Extra data`.
        """
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        raise ValueError("no JSON object found in judge response")

    def _error(self, msg: str) -> GraderResult:
        logger.error("LlmJudgeGrader '%s': %s", self.name, msg)
        return GraderResult(
            grader_name=self.name,
            score=0.0,
            passed=False,
            reason=f"JUDGE_ERROR: {msg}",
        )


register_grader("llm_judge", LlmJudgeGrader)
