"""Position-bias analysis: first-slot win rate and swap-pair consistency."""

import pytest

from judgecal.position import analyze_position

from conftest import rec, swap_pair


def test_first_win_rate_over_decisive_only():
    records = [rec("a")] * 6 + [rec("b")] * 2 + [rec("tie")] * 2
    result = analyze_position(records)
    assert result.n_decisive == 8
    assert result.first_wins == 6
    assert result.first_win_rate == pytest.approx(0.75)
    assert result.delta == pytest.approx(0.25)
    assert result.n_ties == 2


def test_significance_tracks_the_imbalance():
    balanced = analyze_position([rec("a")] * 50 + [rec("b")] * 50)
    assert balanced.p_value == pytest.approx(1.0)
    assert balanced.ci_low < 0.5 < balanced.ci_high
    extreme = analyze_position([rec("a")] * 95 + [rec("b")] * 5)
    assert extreme.p_value < 1e-15


def test_empty_input_yields_none_metrics():
    result = analyze_position([])
    assert result.first_win_rate is None
    assert result.p_value is None
    assert result.n_pairs == 0


def test_swap_pair_flip_is_consistent():
    # Verdict a then b with sides exchanged = same model won both times.
    result = analyze_position(swap_pair("q1", "a", "b"))
    assert result.n_pairs == 1
    assert result.consistent == 1
    assert result.consistency_rate == 1.0


def test_swap_pair_slot_locked_verdicts_are_sticky():
    both_a = analyze_position(swap_pair("q1", "a", "a"))
    assert both_a.first_sticky == 1 and both_a.consistent == 0
    both_b = analyze_position(swap_pair("q1", "b", "b"))
    assert both_b.second_sticky == 1


def test_swap_pair_tie_handling():
    both_ties = analyze_position(swap_pair("q1", "tie", "tie"))
    assert both_ties.consistent == 1          # tie both ways is order-blind
    one_tie = analyze_position(swap_pair("q2", "a", "tie"))
    assert one_tie.mixed == 1
    assert one_tie.consistency_rate == 0.0


def test_pairing_requires_actually_exchanged_sides():
    # Same pair_id but identical orientation both times: no swap pair.
    records = [
        rec("a", pair_id="q1", model_a="m1", model_b="m2"),
        rec("a", pair_id="q1", model_a="m1", model_b="m2"),
    ]
    assert analyze_position(records).n_pairs == 0
    # Exchanged sides but no pair_id: nothing links the rows.
    unlinked = [rec("a", model_a="m1", model_b="m2"), rec("b", model_a="m2", model_b="m1")]
    assert analyze_position(unlinked).n_pairs == 0


def test_pairing_works_from_swapped_flag_without_models():
    records = [
        rec("a", pair_id="q1", swapped=False),
        rec("a", pair_id="q1", swapped=True),
    ]
    result = analyze_position(records)
    assert result.n_pairs == 1
    assert result.first_sticky == 1


def test_group_with_four_rows_yields_two_pairs():
    records = swap_pair("q1", "a", "b") + swap_pair("q1", "b", "a")
    result = analyze_position(records)
    assert result.n_pairs == 2
    assert result.consistent == 2
