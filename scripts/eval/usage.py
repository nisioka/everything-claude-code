"""UsageSnapshot — token usage from a single API call (Requirements 8.1–8.3).

Kept out of executors/__init__.py to avoid an import cycle (executors -> usage -> ...).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UsageSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def cache_hit_ratio(self) -> float:
        """Cache reads as a share of all input tokens that touched the cache layer.

        Defined as cache_read / (cache_read + cache_creation). When neither has tokens
        (e.g. small SKILL.md below the model's cache minimum) the ratio is 0.0.
        """
        denom = self.cache_read_input_tokens + self.cache_creation_input_tokens
        if denom == 0:
            return 0.0
        return self.cache_read_input_tokens / denom

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens
