"""AnthropicExecutor — Claude Messages API with prompt caching + retry (Reqs 2.3–2.6, 8.1, 8.4).

Design notes:
- The system prompt is built as up to two cached `text` blocks: fixed instructions
  first, then the SKILL.md body. Both blocks carry `cache_control: ephemeral` so a
  cache hit on the second task in a run is automatic when the SKILL.md exceeds the
  model's minimum cache size.
- All API calls go through RetryHandler so 429 / 5xx are retried with exponential
  backoff while 4xx auth/validation errors fail fast.
- An injectable `client` parameter exists purely for testing — production callers
  pass nothing and the executor builds a real `anthropic.Anthropic()` client which
  reads `ANTHROPIC_API_KEY` from the environment.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import Anthropic

from scripts.eval.errors import MissingApiKeyError
from scripts.eval.executors import ExecutionResult, Executor, register_executor
from scripts.eval.retry import RetryHandler
from scripts.eval.usage import snapshot_from_sdk_usage

logger = logging.getLogger(__name__)

# Generous cap; the goal is "don't truncate skill outputs", not to gate creativity.
DEFAULT_MAX_TOKENS = 4096


class AnthropicExecutor(Executor):
    def __init__(
        self,
        model: str,
        client: Any | None = None,
        retry_handler: RetryHandler | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise MissingApiKeyError(
                "ANTHROPIC_API_KEY is not set; required for the anthropic executor"
            )
        self.model = model
        self.client = client if client is not None else Anthropic()
        self.retry = retry_handler or RetryHandler()
        self.max_tokens = max_tokens

    def run(
        self,
        prompt: str,
        system_instructions: str,
        skill_markdown: str | None,
        *,
        expected: Any | None = None,
    ) -> ExecutionResult:
        system_blocks = self._build_system_blocks(system_instructions, skill_markdown)
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": prompt}],
        )
        response = self.retry.call(lambda: self.client.messages.create(**kwargs))

        text = self._extract_text(response)
        usage = snapshot_from_sdk_usage(response.usage) if getattr(response, "usage", None) else None
        if usage is not None and usage.cache_read_input_tokens == 0 and usage.cache_creation_input_tokens == 0:
            logger.warning(
                "no prompt cache activity (read=0, creation=0) for model %s — "
                "system prompt may be below the model's minimum cache size",
                self.model,
            )
        return ExecutionResult(output=text, usage=usage)

    @staticmethod
    def _build_system_blocks(instructions: str, skill_markdown: str | None) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if instructions:
            blocks.append(
                {"type": "text", "text": instructions, "cache_control": {"type": "ephemeral"}}
            )
        if skill_markdown:
            blocks.append(
                {"type": "text", "text": skill_markdown, "cache_control": {"type": "ephemeral"}}
            )
        if not blocks:
            blocks.append({"type": "text", "text": "", "cache_control": {"type": "ephemeral"}})
        return blocks

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


def _register_if_possible() -> None:
    """Lazy registration: register the type in the registry but don't instantiate.

    The registry stores classes, not instances, so registering doesn't require
    ANTHROPIC_API_KEY at import time. The MissingApiKeyError is raised only when
    `get_executor("anthropic", ...)` actually instantiates AnthropicExecutor.
    """
    register_executor("anthropic", AnthropicExecutor)


_register_if_possible()
