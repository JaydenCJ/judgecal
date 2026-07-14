"""Human-agreement analysis over labeled records."""

import pytest

from judgecal.agreement import analyze_agreement

from conftest import rec


def test_unlabeled_records_are_excluded_and_all_none_degrades():
    records = [rec("a", human="a"), rec("b", human=None), rec("tie")]
    assert analyze_agreement(records).n_labeled == 1
    empty = analyze_agreement([rec("a"), rec("b")])
    assert empty.n_labeled == 0
    assert empty.kappa is None
    assert empty.observed_agreement is None
    assert empty.band is None


def test_perfect_agreement():
    records = [rec("a", human="a"), rec("b", human="b"), rec("tie", human="tie")] * 5
    result = analyze_agreement(records)
    assert result.observed_agreement == 1.0
    assert result.kappa == pytest.approx(1.0)
    assert result.band == "almost perfect"


def test_confusion_matrix_placement():
    records = [rec("a", human="b")] * 3 + [rec("tie", human="a")] * 2 + [rec("b", human="b")]
    result = analyze_agreement(records)
    assert result.confusion["a"]["b"] == 3      # judge rows, human columns
    assert result.confusion["tie"]["a"] == 2
    assert result.confusion["b"]["b"] == 1
    assert result.confusion["b"]["a"] == 0


def test_decisive_only_agreement_and_per_rater_tie_rates():
    records = [
        rec("a", human="a"),      # decisive, agree
        rec("a", human="b"),      # decisive, disagree
        rec("tie", human="a"),    # judge tie -> excluded from decisive view
        rec("b", human="tie"),    # human tie -> excluded from decisive view
    ]
    result = analyze_agreement(records)
    assert result.n_decisive_both == 2
    assert result.decisive_agreement == 0.5
    assert result.judge_tie_rate == pytest.approx(0.25)
    assert result.human_tie_rate == pytest.approx(0.25)


def test_high_raw_agreement_can_still_be_low_kappa():
    # Judge always says "a"; humans say "a" 80% of the time. Raw agreement
    # is 80% but kappa is 0 — exactly the trap kappa exists to catch.
    records = [rec("a", human="a")] * 8 + [rec("a", human="b")] * 2
    result = analyze_agreement(records)
    assert result.observed_agreement == pytest.approx(0.8)
    assert result.kappa == pytest.approx(0.0)


def test_to_dict_rounds_and_carries_all_keys():
    d = analyze_agreement([rec("a", human="a"), rec("a", human="b"), rec("b", human="b")]).to_dict()
    assert set(d) == {
        "n_labeled", "observed_agreement", "kappa", "band", "confusion",
        "n_decisive_both", "decisive_agreement", "judge_tie_rate", "human_tie_rate",
    }
    assert d["observed_agreement"] == pytest.approx(0.6667, abs=1e-4)
