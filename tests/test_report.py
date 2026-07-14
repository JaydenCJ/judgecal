"""Audit assembly, findings thresholds, renderers, and CI gates."""

import json

from judgecal.report import build_audit, check_gates, render_json, render_markdown, render_text

from conftest import rec


def _biased_records(n=40):
    """A small log with an obvious position bias and full human labels.

    The judge model j1 also sits in slot A, so the self-preference section
    has data to work with.
    """
    records = []
    for i in range(n):
        human = "a" if i % 2 == 0 else "b"
        verdict = "a" if i % 4 != 3 else "b"  # judge says "a" 75% of the time
        records.append(rec(verdict, human=human, judge="j1",
                           model_a="j1", model_b="m2", len_a=100 + i, len_b=90))
    return records


def _audit(records, **kwargs):
    return build_audit(records, source="test.jsonl", n_rows=len(records), n_skipped=0, **kwargs)


# --- Audit structure ---------------------------------------------------------

def test_audit_schema_and_overview_inventory():
    audit = _audit(_biased_records(8))
    assert audit["schema_version"] == 1
    assert set(audit) == {
        "schema_version", "judgecal_version", "source", "overview",
        "agreement", "position", "length", "self_preference",
    }
    ov = audit["overview"]
    assert ov["n_parsed"] == 8
    assert ov["judges"] == ["j1"]
    assert ov["models"] == ["j1", "m2"]
    assert ov["verdicts"]["a"] + ov["verdicts"]["b"] + ov["verdicts"]["tie"] == 8


def test_position_flag_fires_on_strong_significant_bias():
    audit = _audit(_biased_records(80))
    levels = [f["level"] for f in audit["position"]["findings"]]
    assert "FLAG" in levels
    assert audit["overview"]["worst_finding"] == "FLAG"


def test_small_sections_report_no_data_instead_of_verdicts():
    audit = _audit([rec("a"), rec("b")])  # no labels, no models, no lengths
    assert audit["agreement"]["finding"]["level"] == "NO DATA"
    assert audit["length"]["finding"]["level"] == "NO DATA"
    assert audit["self_preference"]["finding"]["level"] == "NO DATA"


def test_min_n_is_configurable():
    records = [rec("a", human="a") for _ in range(5)]
    assert _audit(records, min_n=3)["agreement"]["finding"]["level"] != "NO DATA"
    assert _audit(records, min_n=10)["agreement"]["finding"]["level"] == "NO DATA"


def test_self_finding_without_humans_mentions_the_quality_confound():
    records = [rec("a", judge="j1", model_a="j1", model_b="m2") for _ in range(30)]
    finding = _audit(records)["self_preference"]["finding"]
    assert finding["level"] == "FLAG"
    assert "confound" in finding["message"]


def test_self_finding_prefers_the_human_adjusted_delta():
    # Judge and humans agree completely: raw self rate is 100%, but the
    # adjusted delta is 0 -> OK, because quality explains everything.
    records = [rec("a", human="a", judge="j1", model_a="j1", model_b="m2") for _ in range(20)]
    finding = _audit(records)["self_preference"]["finding"]
    assert finding["level"] == "OK"


# --- Renderers ---------------------------------------------------------------

def test_render_json_is_valid_and_sorted():
    audit = _audit(_biased_records())
    text = render_json(audit)
    parsed = json.loads(text)
    assert parsed == json.loads(render_json(audit))  # deterministic
    assert text.index('"agreement"') < text.index('"position"')  # sort_keys


def test_render_text_sections_full_and_filtered():
    full = render_text(_audit(_biased_records()))
    for token in ("[agreement]", "[position]", "[length]", "[self]", "overall:"):
        assert token in full
    only_length = render_text(_audit(_biased_records()), sections=["length"])
    assert "[length]" in only_length
    assert "[agreement]" not in only_length


def test_filtered_render_scopes_the_overall_line_to_printed_sections():
    # Length-biased but position-clean log: `judgecal position` must not end
    # an all-OK position report with the audit-wide FLAG it never printed.
    records = []
    for i in range(40):
        long_first = i % 2 == 0
        records.append(rec("a" if long_first else "b",
                           len_a=200 if long_first else 100,
                           len_b=100 if long_first else 200))
    audit = _audit(records)
    assert render_text(audit).endswith("overall: FLAG")
    assert render_text(audit, sections=["position"]).endswith("overall (position): OK")


def test_render_text_pluralizes_tie_counts():
    # One tie must render as "1 tie", not "1 ties" — cosmetic, but the kind
    # of thing a report you paste into a PR gets judged on.
    one_tie = [rec("a"), rec("a"), rec("tie")]
    out = render_text(_audit(one_tie))
    assert "1 tie)" in out
    assert "1 ties" not in out
    two_ties = [rec("a"), rec("tie"), rec("tie")]
    assert "2 ties)" in render_text(_audit(two_ties))


def test_no_data_messages_use_singular_forms():
    # n=1 flows into the NO DATA explanations; they must stay grammatical.
    audit = _audit([rec("a", human="a")])
    assert "only 1 human-labeled row (" in audit["agreement"]["finding"]["message"]
    assert "only 1 decisive verdict (" in audit["position"]["findings"][0]["message"]


def test_render_markdown_has_summary_table_and_findings():
    out = render_markdown(_audit(_biased_records()))
    assert "| Check | Headline | n | Verdict |" in out
    assert "### Findings" in out
    assert "judgecal audit" in out


# --- Gates --------------------------------------------------------------------

def test_gates_pass_when_thresholds_are_loose_and_absent_gates_never_fire():
    audit = _audit(_biased_records())
    assert check_gates(audit, min_kappa=-1.0, max_position_delta=0.5,
                       max_length_delta=0.5, max_self_delta=0.9) == []
    assert check_gates(audit) == []


def test_gate_min_kappa_fails_with_value_in_message():
    audit = _audit(_biased_records())
    violations = check_gates(audit, min_kappa=0.99)
    assert len(violations) == 1
    assert "--min-kappa" in violations[0]


def test_gate_on_unmeasurable_metric_fails_closed():
    audit = _audit([rec("a"), rec("b")])  # no human labels at all
    violations = check_gates(audit, min_kappa=0.4)
    assert violations and "unavailable" in violations[0]


def test_gate_position_delta_fails_on_biased_log():
    audit = _audit(_biased_records(80))
    violations = check_gates(audit, max_position_delta=0.05)
    assert violations and "delta" in violations[0]
