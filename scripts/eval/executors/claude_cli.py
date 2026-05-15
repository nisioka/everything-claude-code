"""ClaudeCliExecutor — drives evals via the Claude Code CLI (`claude -p`).

The CLI's auth (subscription OAuth or `ANTHROPIC_API_KEY`) is reused as-is, so
running this executor against a Max-plan account uses subscription quota rather
than API billing. Tool use is disabled at invocation time to keep the run as a
pure prompt→completion (the eval harness has no agentic loop to drive).
"""

from __future__ import annotations

import logging
from typing import Any

from scripts.eval.claude_cli_runner import DEFAULT_TIMEOUT_SEC, run_claude_cli
from scripts.eval.executors import ExecutionResult, Executor, register_executor

logger = logging.getLogger(__name__)

_FALLBACK_SYSTEM_PROMPT = (
    "You are evaluating a Claude Code skill. Follow the user's prompt and any "
    "embedded instructions exactly. Respond with the requested output only."
)


class ClaudeCliExecutor(Executor):
    def __init__(self, model: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> None:
        self.model = model
        self.timeout_sec = timeout_sec

    def run(
        self,
        prompt: str,
        system_instructions: str,
        skill_markdown: str | None,
        *,
        expected: Any | None = None,
    ) -> ExecutionResult:
        system_prompt = self._build_system_prompt(system_instructions, skill_markdown)
        cli_result = run_claude_cli(
            prompt=prompt,
            system_prompt=system_prompt,
            model=self.model,
            timeout_sec=self.timeout_sec,
        )

        usage = cli_result.usage
        if usage.cache_read_input_tokens == 0 and usage.cache_creation_input_tokens == 0:
            logger.warning(
                "no prompt cache activity (read=0, creation=0) for model %s — "
                "system prompt may be below the minimum cache size",
                self.model,
            )
        return ExecutionResult(output=cli_result.text, usage=usage)

    @staticmethod
    def _build_system_prompt(instructions: str, skill_markdown: str | None) -> str:
        parts: list[str] = []
        if instructions and instructions.strip():
            parts.append(instructions.strip())
        if skill_markdown:
            parts.append(skill_markdown)
        if not parts:
            return _FALLBACK_SYSTEM_PROMPT
        return "\n\n---\n\n".join(parts)


register_executor("claude_cli", ClaudeCliExecutor)
