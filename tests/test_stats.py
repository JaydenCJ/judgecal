"""The statistics core, checked against hand-computed textbook values.

If these are wrong, every report judgecal prints is wrong, so several tests
pin exact closed-form values rather than loose ranges.
"""

import math

import pytest

from judgecal.stats import (
    binom_two_sided,
    cohen_kappa,
    confusion_matrix,
    kappa_band,
    mean,
    pearson,
    proportion,
    wilson_interval,
)


# --- Cohen's kappa ---------------------------------------------------------

def test_kappa_matches_cohen_1960_worked_example():
    # 2x2 marginals: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no.
    # po = 35/50 = 0.7, pe = (25*30 + 25*20)/2500 = 0.5 -> kappa = 0.4 exactly.
    pairs = [("y", "y")] * 20 + [("y", "n")] * 5 + [("n", "y")] * 10 + [("n", "n")] * 15
    assert cohen_kappa(pairs) == pytest.approx(0.4)


def test_kappa_perfect_agreement_including_constant_raters():
    assert cohen_kappa([("a", "a"), ("b", "b"), ("tie", "tie")] * 4) == pytest.approx(1.0)
    # Both raters constant and agreeing: pe would be 1.0 -> undefined;
    # convention says perfect agreement stays 1.0.
    assert cohen_kappa([("a", "a")] * 7) == pytest.approx(1.0)


def test_kappa_chance_is_zero_and_systematic_disagreement_negative():
    # Independent raters, uniform over two labels: po = pe = 0.5 -> kappa 0.
    chance = [("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")] * 5
    assert cohen_kappa(chance) == pytest.approx(0.0)
    assert cohen_kappa([("a", "b"), ("b", "a")] * 10) < 0


def test_kappa_three_labels_and_empty_input():
    pairs = [("a", "a")] * 10 + [("b", "b")] * 10 + [("tie", "tie")] * 10 + [("a", "b")] * 6
    kappa = cohen_kappa(pairs)
    assert kappa is not None and 0.5 < kappa < 1.0
    assert cohen_kappa([]) is None


def test_kappa_band_boundaries():
    assert kappa_band(-0.1) == "worse than chance"
    assert kappa_band(0.10) == "slight"
    assert kappa_band(0.20) == "fair"
    assert kappa_band(0.40) == "moderate"
    assert kappa_band(0.60) == "substantial"
    assert kappa_band(0.80) == "almost perfect"


# --- Exact binomial test ---------------------------------------------------

def test_binom_exact_known_values():
    # Two-sided p for k=8, n=10, p=0.5 is 2 * (45+10+1)/1024 = 0.109375.
    assert binom_two_sided(8, 10) == pytest.approx(0.109375, abs=1e-9)
    # k=10, n=10: both extreme tails, 2/1024.
    assert binom_two_sided(10, 10) == pytest.approx(2 / 1024, abs=1e-9)
    # Perfectly balanced outcome: every outcome is at most as likely -> 1.0.
    assert binom_two_sided(5, 10) == pytest.approx(1.0)
    # And the two-sided test is symmetric around one half.
    assert binom_two_sided(3, 12) == pytest.approx(binom_two_sided(9, 12), abs=1e-12)


def test_binom_empty_sample_and_out_of_range():
    assert binom_two_sided(0, 0) == 1.0  # no data is no evidence
    with pytest.raises(ValueError):
        binom_two_sided(11, 10)


def test_binom_large_n_stays_finite_and_tiny():
    # 60% wins over 10k trials: astronomically significant, still a valid float.
    p = binom_two_sided(6000, 10000)
    assert 0.0 <= p < 1e-80


# --- Wilson interval -------------------------------------------------------

def test_wilson_interval_known_value():
    # Classic check: 8/10 -> approximately (0.4902, 0.9433).
    low, high = wilson_interval(8, 10)
    assert low == pytest.approx(0.4902, abs=2e-3)
    assert high == pytest.approx(0.9433, abs=2e-3)


def test_wilson_interval_bounds_edges_and_shrinkage():
    for k, n in [(0, 10), (5, 10), (10, 10), (1, 3), (499, 1000)]:
        low, high = wilson_interval(k, n)
        assert low <= k / n <= high
        assert 0.0 <= low <= high <= 1.0
    assert wilson_interval(0, 5)[0] == 0.0      # exact boundary, no float noise
    assert wilson_interval(5, 5)[1] == 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)  # no trials: total uncertainty
    small = wilson_interval(6, 10)
    large = wilson_interval(600, 1000)
    assert (large[1] - large[0]) < (small[1] - small[0])


# --- Pearson correlation ---------------------------------------------------

def test_pearson_perfect_correlations_and_clamping():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert pearson(xs, [2.0, 4.0, 6.0, 8.0]) == pytest.approx(1.0)
    assert pearson(xs, [8.0, 6.0, 4.0, 2.0]) == pytest.approx(-1.0)
    r = pearson([math.log(x) for x in (1.5, 2.5, 0.4, 0.9, 3.0)],
                [1.0, 1.0, -1.0, -1.0, 1.0])
    assert r is not None and -1.0 <= r <= 1.0


def test_pearson_undefined_cases():
    assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None  # zero variance x
    assert pearson([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) is None  # zero variance y
    assert pearson([1.0], [1.0]) is None                       # one point
    with pytest.raises(ValueError):
        pearson([1.0, 2.0], [1.0])


# --- Small helpers ---------------------------------------------------------

def test_confusion_matrix_and_safe_ratios():
    matrix = confusion_matrix([("a", "b"), ("a", "b"), ("tie", "a")], ("a", "b", "tie"))
    assert matrix["a"]["b"] == 2
    assert matrix["tie"]["a"] == 1
    assert matrix["b"]["b"] == 0
    assert proportion(1, 0) is None
    assert proportion(3, 4) == 0.75
    assert mean([]) is None
    assert mean([1.0, 2.0, 3.0]) == 2.0
