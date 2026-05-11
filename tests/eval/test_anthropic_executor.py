"""Tests for AnthropicExecutor (task 6.3 + 6.4 integration via mocked SDK)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from anthropic import APIStatusError, RateLimitError

from scripts.eval.errors import MissingApiKeyError


def _resp(status: int) -> httpx.Response:
    req = httpx.Request("POST", "https://example.test/v1/messages")
    return httpx.Response(status_code=status, request=req)


def _fake_sdk_response(text: str, *, cache_creation: int = 0, cache_read: int = 0):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        ),
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
    )


class _FakeMessages:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeAnthropic:
    def __init__(self, responses) -> None:
        self.messages = _FakeMessages(responses)


# ---- Auth -----------------------------------------------------------------


def test_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from scripts.eval.executors.anthropic import AnthropicExecutor

    with pytest.raises(MissingApiKeyError):
        AnthropicExecutor(model="claude-sonnet-4-6")


def test_uses_env_api_key(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    AnthropicExecutor(model="claude-sonnet-4-6")  # should not raise


# ---- Successful run -------------------------------------------------------


def test_run_returns_text_and_usage(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    fake = _FakeAnthropic([_fake_sdk_response("feat: add x", cache_creation=4096)])
    ex = AnthropicExecutor(model="claude-sonnet-4-6", client=fake)
    result = ex.run(
        prompt="Generate a commit",
        system_instructions="You are a tool.",
        skill_markdown="# Skill\nuse Conventional Commits.",
    )
    assert result.output == "feat: add x"
    assert result.usage is not None
    assert result.usage.cache_creation_input_tokens == 4096


def test_system_built_as_two_cached_blocks(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    fake = _FakeAnthropic([_fake_sdk_response("ok")])
    ex = AnthropicExecutor(model="claude-sonnet-4-6", client=fake)
    ex.run(prompt="p", system_instructions="instr", skill_markdown="skill body")

    call = fake.messages.calls[0]
    sys_param = call["system"]
    assert isinstance(sys_param, list)
    assert len(sys_param) == 2
    for block in sys_param:
        assert block["type"] == "text"
        assert block["cache_control"] == {"type": "ephemeral"}
    assert sys_param[0]["text"] == "instr"
    assert sys_param[1]["text"] == "skill body"


def test_system_omits_skill_block_when_no_markdown(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    fake = _FakeAnthropic([_fake_sdk_response("ok")])
    ex = AnthropicExecutor(model="claude-sonnet-4-6", client=fake)
    ex.run(prompt="p", system_instructions="instr", skill_markdown=None)

    sys_param = fake.messages.calls[0]["system"]
    assert len(sys_param) == 1
    assert sys_param[0]["text"] == "instr"


# ---- Cache observability --------------------------------------------------


def test_warn_when_cache_min_unmet(monkeypatch, caplog) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    fake = _FakeAnthropic([_fake_sdk_response("ok", cache_creation=0, cache_read=0)])
    ex = AnthropicExecutor(model="claude-sonnet-4-6", client=fake)
    with caplog.at_level("WARNING"):
        ex.run(prompt="p", system_instructions="instr", skill_markdown="tiny")
    assert any("cache" in r.message.lower() for r in caplog.records)


def test_no_warn_when_cache_creation_present(monkeypatch, caplog) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    fake = _FakeAnthropic([_fake_sdk_response("ok", cache_creation=4096)])
    ex = AnthropicExecutor(model="claude-sonnet-4-6", client=fake)
    with caplog.at_level("WARNING"):
        ex.run(prompt="p", system_instructions="instr", skill_markdown="big")
    assert not any("cache" in r.message.lower() for r in caplog.records)


def test_cache_creation_then_cache_read_across_two_calls(monkeypatch) -> None:
    """Simulates the canonical flow: call 1 writes cache, call 2 reads it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors.anthropic import AnthropicExecutor

    fake = _FakeAnthropic(
        [
            _fake_sdk_response("first", cache_creation=4096, cache_read=0),
            _fake_sdk_response("second", cache_creation=0, cache_read=4096),
        ]
    )
    ex = AnthropicExecutor(model="claude-sonnet-4-6", client=fake)
    r1 = ex.run(prompt="p1", system_instructions="instr", skill_markdown="big")
    r2 = ex.run(prompt="p2", system_instructions="instr", skill_markdown="big")
    assert r1.usage.cache_creation_input_tokens == 4096
    assert r1.usage.cache_read_input_tokens == 0
    assert r2.usage.cache_creation_input_tokens == 0
    assert r2.usage.cache_read_input_tokens == 4096


# ---- Retry integration ----------------------------------------------------


def test_retry_after_429_eventually_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda *_: None)
    from scripts.eval.executors.anthropic import AnthropicExecutor
    from scripts.eval.retry import RetryHandler

    fake = _FakeAnthropic(
        [
            RateLimitError("rl", response=_resp(429), body=None),
            _fake_sdk_response("recovered"),
        ]
    )
    ex = AnthropicExecutor(
        model="claude-sonnet-4-6",
        client=fake,
        retry_handler=RetryHandler(max_attempts=3, initial_backoff=0),
    )
    res = ex.run(prompt="p", system_instructions="i", skill_markdown=None)
    assert res.output == "recovered"


def test_retry_exhausts_then_raises(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda *_: None)
    from scripts.eval.executors.anthropic import AnthropicExecutor
    from scripts.eval.retry import RetryHandler

    fake = _FakeAnthropic([RateLimitError("rl", response=_resp(429), body=None)] * 3)
    ex = AnthropicExecutor(
        model="claude-sonnet-4-6",
        client=fake,
        retry_handler=RetryHandler(max_attempts=3, initial_backoff=0),
    )
    with pytest.raises(RateLimitError):
        ex.run(prompt="p", system_instructions="i", skill_markdown=None)


def test_4xx_does_not_retry(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("scripts.eval.retry.time.sleep", lambda *_: None)
    from scripts.eval.executors.anthropic import AnthropicExecutor
    from scripts.eval.retry import RetryHandler

    fake = _FakeAnthropic([APIStatusError("auth", response=_resp(401), body=None)])
    ex = AnthropicExecutor(
        model="claude-sonnet-4-6",
        client=fake,
        retry_handler=RetryHandler(max_attempts=3, initial_backoff=0),
    )
    with pytest.raises(APIStatusError):
        ex.run(prompt="p", system_instructions="i", skill_markdown=None)
    assert len(fake.messages.calls) == 1


# ---- Registry self-registration ------------------------------------------


def test_anthropic_executor_self_registers(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from scripts.eval.executors import EXECUTOR_REGISTRY

    assert "anthropic" in EXECUTOR_REGISTRY
