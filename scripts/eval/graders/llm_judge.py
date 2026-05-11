"""LlmJudgeGrader — Anthropic-backed rubric judge with structured JSON output (Reqs 3.4, 3.7).

Failure modes are folded into a single `JUDGE_ERROR: ...` GraderResult so the
Orchestrator's existing `summarise_status` rule promotes the task to `error` without
needing to know about LLM-specific failures.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from anthropic import Anthropic, APIStatusError, RateLimitError

from scripts.eval.graders import Grader, GraderResult, register_grader
from scripts.eval.retry import RetryHandler

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024

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
        client: Any | None = None,
        retry_handler: RetryHandler | None = None,
    ) -> None:
        self.name = name
        self.rubric = config.get("rubric", "")
        self.judge_model = config.get("judge_model", DEFAULT_JUDGE_MODEL)
        self.max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
        self.threshold = float(config.get("pass_threshold", 0.5))

        # Lazy client: judge is independent of the main executor (different model OK).
        # Don't error on missing API key here — surface as JUDGE_ERROR at grade time so a
        # mock-only run doesn't crash if a YAML file happens to declare a judge grader.
        self._client = client
        self.retry = retry_handler or RetryHandler()

    def grade(self, output: str, expected: Any, context: dict[str, Any]) -> GraderResult:
        try:
            client = self._get_client()
        except Exception as e:
            return self._error(f"client unavailable: {e}")

        prompt = self._build_prompt(output, expected)

        try:
            response = self.retry.call(
                lambda: client.messages.create(
                    model=self.judge_model,
                    max_tokens=self.max_tokens,
                    system=_JUDGE_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
            )
        except (APIStatusError, RateLimitError) as e:
            return self._error(f"judge API failed: {e}")
        except Exception as e:  # noqa: BLE001 — surface anything from the network call
            return self._error(f"judge call raised: {e}")

        text = self._extract_text(response)
        try:
            data = self._parse_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            return self._error(f"could not parse judge response as JSON: {e}; raw={text[:200]!r}")

        try:
            score = float(data["score"])
            reason = data["reason"]
        except (KeyError, TypeError, ValueError) as e:
            return self._error(f"judge JSON missing required keys: {e}; raw={text[:200]!r}")

        if not isinstance(reason, str) or not reason.strip():
            return self._error(f"judge JSON `reason` is empty or non-string; raw={text[:200]!r}")
        if not 0.0 <= score <= 1.0:
            return self._error(f"judge JSON `score` out of range (0..1): {score}")

        return GraderResult(
            grader_name=self.name,
            score=score,
            passed=score >= self.threshold,
            reason=reason,
        )

    # ---- helpers ---------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = Anthropic()
        return self._client

    def _build_prompt(self, output: str, expected: Any) -> str:
        expected_repr = expected if isinstance(expected, str) else json.dumps(expected, ensure_ascii=False)
        return (
            f"Rubric:\n{self.rubric}\n\n"
            f"Expected (may be empty):\n{expected_repr}\n\n"
            f"Model output:\n{output}\n\n"
            f"Return JSON: {{\"score\": <float 0..1>, \"reason\": <string>}}"
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None) or (
                block.get("type") if isinstance(block, dict) else None
            )
            if block_type != "text":
                continue
            text = getattr(block, "text", None) if not isinstance(block, dict) else block.get("text")
            if text:
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extract a JSON object from the response — tolerates code fences / prose wrap."""
        # Try direct parse first.
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # Fall back: grab the first {...} block, ignoring code-fence markers.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("no JSON object found in judge response")
        return json.loads(match.group(0))

    def _error(self, msg: str) -> GraderResult:
        logger.error("LlmJudgeGrader '%s': %s", self.name, msg)
        return GraderResult(
            grader_name=self.name,
            score=0.0,
            passed=False,
            reason=f"JUDGE_ERROR: {msg}",
        )


register_grader("llm_judge", LlmJudgeGrader)
