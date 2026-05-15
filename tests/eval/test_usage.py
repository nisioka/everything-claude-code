"""Tests for UsageSnapshot and the SDK adapter (task 6.2)."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.eval.usage import UsageSnapshot, snapshot_from_sdk_usage


def test_cache_hit_ratio_zero_when_no_cache() -> None:
    s = UsageSnapshot(input_tokens=100, output_tokens=20)
    assert s.cache_hit_ratio == 0.0


def test_cache_hit_ratio_with_only_creation() -> None:
    """First call: cache write only, no reads → hit ratio 0."""
    s = UsageSnapshot(input_tokens=100, output_tokens=20, cache_creation_input_tokens=4096)
    assert s.cache_hit_ratio == 0.0


def test_cache_hit_ratio_with_only_reads() -> None:
    """Subsequent call: only reads, no writes → hit ratio 1."""
    s = UsageSnapshot(input_tokens=10, output_tokens=20, cache_read_input_tokens=4096)
    assert s.cache_hit_ratio == 1.0


def test_cache_hit_ratio_mixed() -> None:
    s = UsageSnapshot(
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=300,
        cache_creation_input_tokens=100,
    )
    assert s.cache_hit_ratio == 0.75


def test_total_input_tokens_includes_cache_layers() -> None:
    s = UsageSnapshot(
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=300,
        cache_creation_input_tokens=100,
    )
    assert s.total_input_tokens == 410


def test_snapshot_from_sdk_usage_full() -> None:
    sdk_usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=300,
        cache_creation_input_tokens=100,
    )
    s = snapshot_from_sdk_usage(sdk_usage)
    assert s.input_tokens == 10
    assert s.output_tokens == 20
    assert s.cache_read_input_tokens == 300
    assert s.cache_creation_input_tokens == 100


def test_snapshot_from_sdk_usage_handles_missing_cache_fields() -> None:
    """Older SDK responses or older models may omit cache fields entirely."""
    sdk_usage = SimpleNamespace(input_tokens=10, output_tokens=20)
    s = snapshot_from_sdk_usage(sdk_usage)
    assert s.cache_read_input_tokens == 0
    assert s.cache_creation_input_tokens == 0
