"""Self-preference analysis: model-name matching and the human baseline."""

import pytest

from judgecal.selfpref import analyze_self_preference, normalize_model, same_family

from conftest import rec


# --- Name matching ----------------------------------------------------------

def test_normalize_model_folds_case_and_separators():
    assert normalize_model("Aurora_8B") == "aurora-8b"
    assert normalize_model("  aurora/8b ") == "aurora-8b"
    assert normalize_model("aurora.8b") == "aurora-8b"


def test_same_family_matches_variants_only_at_separator_boundaries():
    assert same_family("aurora-8b", "Aurora_8B")
    assert same_family("aurora-8b", "aurora-8b-instruct")
    assert same_family("aurora-8b-instruct", "aurora-8b")
    # "aurora-8" must not swallow "aurora-80b".
    assert not same_family("aurora-8", "aurora-80b")
    assert not same_family("aurora", "auroral")


# --- Analysis ---------------------------------------------------------------

def test_self_rows_need_judge_and_both_models():
    records = [
        rec("a", judge="j1", model_a="j1", model_b="m2"),  # counted
        rec("a", judge="j1", model_a="j1"),                # missing model_b
        rec("a", model_a="j1", model_b="m2"),              # missing judge
    ]
    assert analyze_self_preference(records).n_self == 1
    # No self rows at all: metrics degrade to None, never crash.
    other = analyze_self_preference([rec("a", judge="j1", model_a="m1", model_b="m2")])
    assert other.n_self == 0
    assert other.self_win_rate is None
    assert other.adjusted_delta is None


def test_both_sides_self_carries_no_signal():
    records = [rec("a", judge="j1", model_a="j1", model_b="j1")]
    assert analyze_self_preference(records).n_self == 0


def test_self_win_rate_and_side_detection():
    records = [
        rec("a", judge="j1", model_a="j1", model_b="m2"),  # self in slot a, wins
        rec("a", judge="j1", model_a="m2", model_b="j1"),  # self in slot b, loses
        rec("b", judge="j1", model_a="m2", model_b="j1"),  # self in slot b, wins
    ]
    result = analyze_self_preference(records)
    assert result.n_self == 3
    assert result.self_wins == 2
    assert result.self_win_rate == pytest.approx(2 / 3)


def test_ties_are_counted_but_not_rated():
    records = [
        rec("tie", judge="j1", model_a="j1", model_b="m2"),
        rec("a", judge="j1", model_a="j1", model_b="m2"),
    ]
    result = analyze_self_preference(records)
    assert result.n_self == 1
    assert result.n_ties == 1


def test_family_matching_is_default_and_exact_mode_is_stricter():
    records = [rec("a", judge="aurora-8b", model_a="aurora-8b-instruct", model_b="m2")]
    assert analyze_self_preference(records, family=True).n_self == 1
    assert analyze_self_preference(records, family=False).n_self == 0


def test_human_baseline_nets_out_quality():
    # Judge picks itself 4/4; humans pick it 2/4 on the same rows.
    records = [
        rec("a", human="a", judge="j1", model_a="j1", model_b="m2"),
        rec("a", human="a", judge="j1", model_a="j1", model_b="m2"),
        rec("a", human="b", judge="j1", model_a="j1", model_b="m2"),
        rec("a", human="b", judge="j1", model_a="j1", model_b="m2"),
    ]
    result = analyze_self_preference(records)
    assert result.self_win_rate == 1.0
    assert result.human_self_rate == pytest.approx(0.5)
    assert result.adjusted_delta == pytest.approx(0.5)


def test_judges_matched_lists_unique_names():
    records = [
        rec("a", judge="j1", model_a="j1", model_b="m2"),
        rec("b", judge="j2", model_a="m3", model_b="j2"),
        rec("a", judge="j1", model_a="j1", model_b="m3"),
    ]
    assert analyze_self_preference(records).judges_matched == ["j1", "j2"]
