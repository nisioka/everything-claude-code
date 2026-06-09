"""UsageSnapshot — token usage from a single API call.

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
        """Cache-read share of cache-eligible tokens.

        Formula: `cache_read / (cache_read + cache_creation)` — i.e. of the tokens
        that did interact with the cache layer, what fraction was a hit (read) vs a
        write (creation). `input_tokens` (uncached input) is intentionally excluded
        from the denominator so the ratio measures cache effectiveness, not the
        share of total input that was cached.

        Returns 0.0 when neither counter has tokens — e.g. a small SKILL.md below
        the model's minimum cache size.
        """
        denom = self.cache_read_input_tokens + self.cache_creation_input_tokens
        if denom == 0:
            return 0.0
        return self.cache_read_input_tokens / denom

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens


def snapshot_from_sdk_usage(usage: object) -> UsageSnapshot:
    """Convert an Anthropic SDK `usage` object into a UsageSnapshot.

    Older models / SDK versions may omit the cache fields; treat missing as 0
    so callers don't crash on partial responses.
    """
    return UsageSnapshot(
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )
