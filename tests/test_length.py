"""Length-bias analysis: longer-win rate, ratio buckets, human adjustment."""

import pytest

from judgecal.length import analyze_length

from conftest import rec


def test_longer_win_rate_counts_the_longer_side():
    records = [
        rec("a", len_a=100, len_b=50),   # longer (a) wins
        rec("b", len_a=100, len_b=50),   # shorter wins
        rec("b", len_a=30, len_b=90),    # longer (b) wins
    ]
    result = analyze_length(records)
    assert result.n_compared == 3
    assert result.longer_wins == 2
    assert result.longer_win_rate == pytest.approx(2 / 3)


def test_rows_without_usable_lengths_are_excluded():
    records = [
        rec("a", len_a=100, len_b=50),
        rec("a"),                          # no lengths
        rec("a", len_a=80, len_b=80),      # equal: "longer" undefined
        rec("tie", len_a=100, len_b=50),   # tie: judge chose neither
        rec("a", len_a=0, len_b=50),       # zero length: degenerate row
    ]
    assert analyze_length(records).n_compared == 1


def test_correlation_positive_when_length_predicts_verdict():
    records = [rec("a", len_a=200 + i, len_b=100) for i in range(10)]
    records += [rec("b", len_a=100, len_b=300 + i) for i in range(10)]
    result = analyze_length(records)
    assert result.correlation is not None and result.correlation > 0.9


def test_correlation_none_when_ratios_are_constant():
    records = [rec("a", len_a=200, len_b=100), rec("b", len_a=200, len_b=100)]
    assert analyze_length(records).correlation is None


def test_buckets_partition_all_compared_rows():
    records = [
        rec("a", len_a=105, len_b=100),   # 1.05x
        rec("a", len_a=130, len_b=100),   # 1.3x
        rec("b", len_a=100, len_b=180),   # 1.8x
        rec("a", len_a=500, len_b=100),   # 5x
    ]
    result = analyze_length(records)
    by_label = {b["bucket"]: b for b in result.buckets}
    assert by_label["<=1.1x"]["n"] == 1
    assert by_label["1.1-1.5x"]["n"] == 1
    assert by_label["1.5-2x"]["n"] == 1
    assert by_label[">2x"]["n"] == 1
    assert sum(b["n"] for b in result.buckets) == result.n_compared


def test_human_adjustment_isolates_the_bias():
    # Judge always picks the longer answer; humans split 50/50 on the same
    # rows. Raw rate 100%, human rate 50% -> adjusted delta +0.5.
    records = [rec("a", human="a", len_a=200, len_b=100) for _ in range(5)]
    records += [rec("a", human="b", len_a=200, len_b=100) for _ in range(5)]
    result = analyze_length(records)
    assert result.longer_win_rate == 1.0
    assert result.human_longer_rate == pytest.approx(0.5)
    assert result.adjusted_delta == pytest.approx(0.5)


def test_human_adjustment_skips_human_ties():
    records = [
        rec("a", human="tie", len_a=200, len_b=100),
        rec("a", human="a", len_a=200, len_b=100),
    ]
    result = analyze_length(records)
    assert result.n_human == 1
    assert result.adjusted_delta == pytest.approx(0.0)


def test_no_labels_and_empty_input_degrade_to_none():
    unlabeled = analyze_length([rec("a", len_a=200, len_b=100)])
    assert unlabeled.adjusted_delta is None
    assert unlabeled.n_human == 0
    empty = analyze_length([])
    assert empty.n_compared == 0
    assert empty.longer_win_rate is None
    assert empty.p_value is None
