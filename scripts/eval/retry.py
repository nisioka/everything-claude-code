"""RetryHandler — exponential backoff for transient Anthropic API errors (Req 8.4).

Retry policy:
- Captures `RateLimitError` (HTTP 429) and `APIStatusError` with `status_code >= 500`
- Default: 3 attempts total, initial backoff 1.0s, doubling between attempts
- 4xx errors (auth, malformed request) bubble up immediately — they will never
  succeed by waiting longer
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from anthropic import APIStatusError, RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryHandler:
    def __init__(self, max_attempts: int = 3, initial_backoff: float = 1.0) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff

    def call(self, fn: Callable[[], T]) -> T:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn()
            except RateLimitError as e:
                last_exc = e
                if attempt == self.max_attempts:
                    logger.error("rate-limited; giving up after %d attempts", attempt)
                    raise
                self._wait(attempt, "rate limit")
            except APIStatusError as e:
                status = getattr(e, "status_code", None) or getattr(
                    getattr(e, "response", None), "status_code", None
                )
                if status is not None and status < 500:
                    raise
                last_exc = e
                if attempt == self.max_attempts:
                    logger.error("server error %s; giving up after %d attempts", status, attempt)
                    raise
                self._wait(attempt, f"server error {status}")
        # Unreachable — loop either returns or raises.
        if last_exc:
            raise last_exc
        raise RuntimeError("RetryHandler.call exited without a result or exception")

    def _wait(self, attempt: int, reason: str) -> None:
        delay = self.initial_backoff * (2 ** (attempt - 1))
        logger.warning("%s (attempt %d/%d); sleeping %.1fs", reason, attempt, self.max_attempts, delay)
        time.sleep(delay)
