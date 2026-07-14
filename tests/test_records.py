"""Log loading: alias resolution, --map overrides, nested shapes, bad lines.

Real judge logs are messy exports; the loader's job is to salvage every row
it can and explain every row it can't, with a line number.
"""

import json

import pytest

from judgecal.records import (
    MappingError,
    filter_judge,
    load_text,
    normalize_verdict,
    parse_mapping,
)


# --- Verdict normalization -------------------------------------------------

def test_verdict_spellings_fold_to_canonical():
    table = {
        "a": "a", "B": "b", "Tie": "tie",
        "model_a": "a", "model_2": "b", "assistant_b": "b",
        "first": "a", "second": "b", "left": "a", "right": "b",
        "1": "a", "2": "b",
        "equal": "tie", "both": "tie", "draw": "tie", "neither": "tie",
    }
    for raw, expected in table.items():
        assert normalize_verdict(raw, None, None) == expected, raw
    assert normalize_verdict(1, None, None) == "a"
    assert normalize_verdict(2, None, None) == "b"


def test_verdict_matching_a_model_name_resolves_to_that_side():
    assert normalize_verdict("Nimbus-9", "nimbus-9", "cobalt-1") == "a"
    assert normalize_verdict("cobalt-1", "nimbus-9", "cobalt-1") == "b"


def test_verdict_bool_and_garbage_are_rejected():
    assert normalize_verdict(True, None, None) is None
    assert normalize_verdict("excellent", None, None) is None
    assert normalize_verdict(3, None, None) is None
    assert normalize_verdict(None, None, None) is None


# --- Field aliases and shapes ----------------------------------------------

def test_minimal_record_via_aliases_and_numeric_pair_id():
    result = load_text('{"winner": "A", "judge_model": "j1", "prompt_id": "q1"}\n'
                       '{"verdict": "b", "pair_id": 42}')
    assert len(result.records) == 2
    first, second = result.records
    assert (first.verdict, first.judge, first.pair_id) == ("a", "j1", "q1")
    assert second.pair_id == "42"  # numeric ids are stringified


def test_text_strings_and_nested_objects_yield_lengths_and_models():
    row = ('{"verdict": "b", '
           '"response_a": {"model": "nimbus-9", "text": "four"}, '
           '"response_b": {"name": "cobalt-1", "tokens": 128}}')
    record = load_text(row).records[0]
    assert record.model_a == "nimbus-9"
    assert record.len_a == 4          # from nested text
    assert record.model_b == "cobalt-1"
    assert record.len_b == 128        # explicit token count wins over text
    plain = load_text('{"verdict": "b", "response_a": "hello", "response_b": "hi there"}').records[0]
    assert (plain.len_a, plain.len_b) == (5, 8)


def test_explicit_fields_beat_derived_and_nested_ones():
    row = ('{"verdict": "a", "text_a": "hello", "len_a": 900, '
           '"model_a": "outer", "response_b": {"model": "inner", "text": "abc"}}')
    record = load_text(row).records[0]
    assert record.len_a == 900        # explicit length beats len("hello")
    assert record.model_a == "outer"
    assert record.model_b == "inner"  # nested fallback still works for side b


def test_swapped_spellings_and_unknown_value_degrades():
    for raw, expected in [("true", True), ("swapped", True), ("ba", True), (True, True),
                          ("false", False), ("original", False), ("ab", False), (False, False)]:
        row = json.dumps({"verdict": "a", "swapped": raw})
        assert load_text(row).records[0].swapped is expected, raw
    result = load_text('{"verdict": "a", "swapped": "maybe"}')
    assert len(result.records) == 1
    assert result.records[0].swapped is None
    assert any(not issue.fatal for issue in result.issues)


# --- --map overrides --------------------------------------------------------

def test_map_override_wins_over_aliases():
    mapping = parse_mapping(["verdict=my_call", "human=verdict"])
    # The alias table would read "verdict" as the judge verdict; the mapping
    # redirects it to my_call and repurposes "verdict" as the human label.
    record = load_text('{"my_call": "a", "verdict": "b"}', mapping).records[0]
    assert record.verdict == "a"
    assert record.human == "b"


def test_mapped_field_ignores_alias_fallback():
    mapping = parse_mapping(["judge=grader_name"])
    record = load_text('{"verdict": "a", "judge": "wrong", "grader_name": "right"}', mapping).records[0]
    assert record.judge == "right"


def test_malformed_map_specs_raise():
    for bad in ("verdict", "=x", "verdict=", "nonsense=key"):
        with pytest.raises(MappingError):
            parse_mapping([bad])


# --- Error handling ---------------------------------------------------------

def test_bad_json_line_is_skipped_with_line_number():
    text = '{"verdict": "a"}\nnot json at all\n{"verdict": "b"}\n'
    result = load_text(text)
    assert [r.verdict for r in result.records] == ["a", "b"]
    assert result.n_skipped == 1
    assert any(issue.line == 2 and issue.fatal for issue in result.issues)


def test_missing_and_unrecognized_verdicts_are_fatal_with_map_hint():
    missing = load_text('{"answer": "a"}')
    assert missing.records == []
    assert "--map" in missing.issues[0].message
    unknown = load_text('{"verdict": "??"}')
    assert unknown.records == []
    assert "unrecognized verdict" in unknown.issues[0].message


def test_field_level_degradations():
    # Unrecognized human label: keep the record, drop the label, warn.
    result = load_text('{"verdict": "a", "human": "great"}')
    assert len(result.records) == 1
    assert result.records[0].human is None
    assert result.n_skipped == 0
    # Negative length: the row is unusable for length analysis -> fatal.
    bad = load_text('{"verdict": "a", "len_a": -5, "len_b": 3}')
    assert bad.records == [] and bad.n_skipped == 1


def test_json_array_input_and_non_object_rows():
    result = load_text('["a", {"verdict": "b"}]')
    assert [r.verdict for r in result.records] == ["b"]
    assert result.n_rows == 2
    assert any("expected a JSON object" in issue.message for issue in result.issues)
    # In JSONL form, blank lines are not rows either.
    jsonl = load_text('\n{"verdict": "a"}\n\n\n{"verdict": "b"}\n')
    assert jsonl.n_rows == 2 and len(jsonl.records) == 2


def test_filter_judge_is_case_insensitive_exact():
    result = load_text('{"verdict": "a", "judge": "Aurora-8B"}\n'
                       '{"verdict": "b", "judge": "other"}\n{"verdict": "tie"}')
    kept = filter_judge(result.records, "aurora-8b")
    assert len(kept) == 1 and kept[0].verdict == "a"
