"""Tests for Grader ABC, registry, RegexGrader, ListMatchGrader, and the aggregator."""

from __future__ import annotations

import pytest

from scripts.eval.errors import UnknownGraderError
from scripts.eval.graders import (
    GRADER_REGISTRY,
    Grader,
    GraderResult,
    aggregate,
    build_grader,
    get_grader,
    register_grader,
    summarise_status,
)
from scripts.eval.graders.list_match import ListMatchGrader
from scripts.eval.graders.regex import RegexGrader


# ---- Schema / registry -----------------------------------------------------


def test_grader_result_has_required_fields() -> None:
    r = GraderResult(grader_name="r", score=1.0, passed=True, reason="ok")
    assert r.grader_name == "r"
    assert r.score == 1.0
    assert r.passed is True
    assert r.reason == "ok"


def test_register_and_get_grader() -> None:
    class _Dummy(Grader):
        def grade(self, output, expected, context):
            return GraderResult(grader_name="x", score=1.0, passed=True, reason="ok")

    register_grader("_dummy", _Dummy)
    try:
        cls = get_grader("_dummy")
        assert cls is _Dummy
    finally:
        GRADER_REGISTRY.pop("_dummy", None)


def test_get_unknown_grader_raises() -> None:
    with pytest.raises(UnknownGraderError):
        get_grader("nope")


def test_build_grader_constructs_known_types() -> None:
    rg = build_grader(name="r", grader_type="regex", config={"pattern": "x", "mode": "match"})
    assert isinstance(rg, RegexGrader)

    lm = build_grader(
        name="l",
        grader_type="list_match",
        config={"expected_items": ["a"], "mode": "exact"},
    )
    assert isinstance(lm, ListMatchGrader)


def test_abc_rejects_subclass_without_grade() -> None:
    class _Broken(Grader):
        pass

    with pytest.raises(TypeError):
        _Broken()  # type: ignore[abstract]


# ---- RegexGrader -----------------------------------------------------------


def test_regex_grader_match_pass() -> None:
    g = RegexGrader(name="r", config={"pattern": r"^feat:\s", "mode": "match"})
    res = g.grade(output="feat: add x", expected=None, context={})
    assert res.score == 1.0
    assert res.passed is True


def test_regex_grader_match_fail() -> None:
    g = RegexGrader(name="r", config={"pattern": r"^feat:", "mode": "match"})
    res = g.grade(output="docs: update", expected=None, context={})
    assert res.score == 0.0
    assert res.passed is False


def test_regex_grader_no_match_mode_pass_when_absent() -> None:
    g = RegexGrader(name="r", config={"pattern": r"\[[A-Z]+-\d+\]", "mode": "no_match"})
    res = g.grade(output="add new page", expected=None, context={})
    assert res.score == 1.0
    assert res.passed is True


def test_regex_grader_no_match_mode_fail_when_present() -> None:
    g = RegexGrader(name="r", config={"pattern": r"\[[A-Z]+-\d+\]", "mode": "no_match"})
    res = g.grade(output="[PROJ-1] do thing", expected=None, context={})
    assert res.score == 0.0
    assert res.passed is False


def test_regex_grader_supports_string_flags() -> None:
    g = RegexGrader(
        name="r",
        config={"pattern": "^feat", "mode": "match", "flags": ["IGNORECASE", "MULTILINE"]},
    )
    res = g.grade(output="docs: top\nFEAT: second line", expected=None, context={})
    assert res.passed is True


def test_regex_grader_invalid_pattern_returns_error_result() -> None:
    g = RegexGrader(name="r", config={"pattern": "(unclosed", "mode": "match"})
    res = g.grade(output="anything", expected=None, context={})
    assert res.score == 0.0
    assert res.passed is False
    assert "GRADER_ERROR" in res.reason


def test_regex_grader_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        RegexGrader(name="r", config={"pattern": ".*", "mode": "fuzzy"})


# ---- ListMatchGrader -------------------------------------------------------


def test_list_match_exact_pass() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": ["a", "b"], "mode": "exact"},
    )
    res = g.grade(output="a\nb", expected=None, context={})
    assert res.passed is True
    assert res.score == 1.0


def test_list_match_exact_fail_on_missing_item() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": ["a", "b"], "mode": "exact"},
    )
    res = g.grade(output="a", expected=None, context={})
    assert res.passed is False
    assert res.score == 0.0


def test_list_match_superset_pass_when_extra_items_present() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": [".env", "credentials.json"], "mode": "superset"},
    )
    res = g.grade(output=".env\ncredentials.json\nextra.key", expected=None, context={})
    assert res.passed is True


def test_list_match_superset_fail_when_required_missing() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": [".env"], "mode": "superset"},
    )
    res = g.grade(output="readme.md", expected=None, context={})
    assert res.passed is False


def test_list_match_subset_pass_when_strict_subset() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": ["a", "b", "c"], "mode": "subset"},
    )
    res = g.grade(output="a\nb", expected=None, context={})
    assert res.passed is True


def test_list_match_subset_fail_when_extra_present() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": ["a", "b"], "mode": "subset"},
    )
    res = g.grade(output="a\nb\nz", expected=None, context={})
    assert res.passed is False


def test_list_match_json_array_parse_mode() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": [".env"], "mode": "exact", "parse_mode": "json_array"},
    )
    res = g.grade(output='[".env"]', expected=None, context={})
    assert res.passed is True


def test_list_match_json_array_invalid_input_errors() -> None:
    g = ListMatchGrader(
        name="l",
        config={"expected_items": [".env"], "mode": "exact", "parse_mode": "json_array"},
    )
    res = g.grade(output="not json", expected=None, context={})
    assert res.passed is False
    assert "GRADER_ERROR" in res.reason


def test_list_match_exact_empty_when_output_empty() -> None:
    """sensitive-file クリーンケース: 検出件数 0 を expected_items=[] で確認できる。"""
    g = ListMatchGrader(name="l", config={"expected_items": [], "mode": "exact"})
    res = g.grade(output="", expected=None, context={})
    assert res.passed is True


def test_list_match_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        ListMatchGrader(name="l", config={"expected_items": [], "mode": "fuzzy"})


# ---- Aggregation -----------------------------------------------------------


def _gr(name: str, score: float) -> GraderResult:
    return GraderResult(grader_name=name, score=score, passed=score >= 0.5, reason="x")


def test_aggregate_weighted_average() -> None:
    results = [_gr("a", 1.0), _gr("b", 0.0)]
    weights = [2.0, 1.0]
    assert aggregate(results, weights) == pytest.approx(2.0 / 3.0)


def test_aggregate_handles_zero_total_weight() -> None:
    """Defensive: zero weight should not blow up — return 0.0 deterministically."""
    assert aggregate([], []) == 0.0


def test_summarise_status_pass_above_threshold() -> None:
    results = [_gr("a", 1.0)]
    assert summarise_status(results, weights=[1.0], threshold=0.5) == "pass"


def test_summarise_status_fail_below_threshold() -> None:
    results = [_gr("a", 0.4)]
    assert summarise_status(results, weights=[1.0], threshold=0.5) == "fail"


def test_summarise_status_error_when_any_grader_errors() -> None:
    """A single GRADER_ERROR / JUDGE_ERROR result should mark the task error."""
    error = GraderResult(grader_name="x", score=0.0, passed=False, reason="JUDGE_ERROR: 5xx")
    ok = _gr("ok", 1.0)
    assert summarise_status([error, ok], weights=[1.0, 1.0], threshold=0.5) == "error"
