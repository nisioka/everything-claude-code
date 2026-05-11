"""Tests for RetryHandler (task 6.1)."""

from __future__ import annotations

import httpx
import pytest
from anthropic import APIStatusError, RateLimitError

from scripts.eval.retry import RetryHandler


def _resp(status: int) -> httpx.Response:
    req = httpx.Request("POST", "https://example.test/v1/messages")
    return httpx.Response(status_code=status, request=req)


def _rate_limit() -> RateLimitError:
    return RateLimitError("rate limited", response=_resp(429), body=None)


def _server_error() -> APIStatusError:
    return APIStatusError("boom", response=_resp(500), body=None)


def _client_error_400() -> APIStatusError:
    return APIStatusError("bad request", response=_resp(400), body=None)


def _client_error_401() -> APIStatusError:
    return APIStatusError("unauth", response=_resp(401), body=None)


def test_retry_passes_through_on_success() -> None:
    rh = RetryHandler(max_attempts=3, initial_backoff=0)
    out = rh.call(lambda: "ok")
    assert out == "ok"


def test_retry_recovers_after_rate_limit() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit()
        return "recovered"

    rh = RetryHandler(max_attempts=3, initial_backoff=0)
    assert rh.call(fn) == "recovered"
    assert calls["n"] == 3


def test_retry_gives_up_after_max_attempts() -> None:
    rh = RetryHandler(max_attempts=3, initial_backoff=0)
    with pytest.raises(RateLimitError):
        rh.call(lambda: (_ for _ in ()).throw(_rate_limit()))


def test_retry_retries_on_5xx() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise _server_error()
        return "ok"

    rh = RetryHandler(max_attempts=3, initial_backoff=0)
    assert rh.call(fn) == "ok"
    assert calls["n"] == 2


def test_retry_bubbles_4xx_immediately() -> None:
    """4xx errors are permanent (auth, malformed request) — no retry."""
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise _client_error_400()

    rh = RetryHandler(max_attempts=3, initial_backoff=0)
    with pytest.raises(APIStatusError):
        rh.call(fn)
    assert calls["n"] == 1


def test_retry_bubbles_401_immediately() -> None:
    rh = RetryHandler(max_attempts=3, initial_backoff=0)
    with pytest.raises(APIStatusError):
        rh.call(lambda: (_ for _ in ()).throw(_client_error_401()))


def test_retry_backoff_doubles(monkeypatch) -> None:
    """Backoff should be initial * 2^(attempt-1): 1, 2, 4, ..."""
    sleeps: list[float] = []
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise _rate_limit()

    rh = RetryHandler(max_attempts=3, initial_backoff=1.0)
    with pytest.raises(RateLimitError):
        rh.call(fn)
    # 3 attempts, 2 sleeps between them
    assert sleeps == [1.0, 2.0]
