"""Load and normalize pairwise judge logs.

judgecal reads JSON Lines (one JSON object per line) or a single JSON array.
Real-world judge logs never agree on field names, so every canonical field
accepts a list of common aliases, and ``--map field=key`` overrides beat the
alias table entirely. Records that cannot be interpreted are skipped with a
line-numbered issue instead of aborting the whole audit — a 200k-row log with
three broken lines should still produce a report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

VERDICT_A = "a"
VERDICT_B = "b"
VERDICT_TIE = "tie"
VERDICTS = (VERDICT_A, VERDICT_B, VERDICT_TIE)

# Canonical field -> accepted source keys, in priority order.
FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "verdict": ("verdict", "choice", "winner", "judgement", "judgment", "preference", "decision", "label"),
    "human": ("human", "human_verdict", "human_label", "human_choice", "gold", "gold_label", "annotation", "annotator_label"),
    "judge": ("judge", "judge_model", "evaluator", "grader"),
    "pair_id": ("pair_id", "prompt_id", "question_id", "group_id", "example_id"),
    "swapped": ("swapped", "swap", "is_swapped", "order"),
    "model_a": ("model_a",),
    "model_b": ("model_b",),
    "text_a": ("response_a", "text_a", "answer_a", "output_a", "completion_a"),
    "text_b": ("response_b", "text_b", "answer_b", "output_b", "completion_b"),
    "len_a": ("len_a", "length_a", "tokens_a"),
    "len_b": ("len_b", "length_b", "tokens_b"),
}

# Verdict spellings seen in the wild, all folded to a/b/tie.
_VERDICT_VALUES: Dict[str, str] = {
    "a": VERDICT_A, "b": VERDICT_B, "tie": VERDICT_TIE,
    "model_a": VERDICT_A, "model_b": VERDICT_B,
    "model_1": VERDICT_A, "model_2": VERDICT_B,
    "assistant_a": VERDICT_A, "assistant_b": VERDICT_B,
    "response_a": VERDICT_A, "response_b": VERDICT_B,
    "first": VERDICT_A, "second": VERDICT_B,
    "left": VERDICT_A, "right": VERDICT_B,
    "1": VERDICT_A, "2": VERDICT_B,
    "equal": VERDICT_TIE, "both": VERDICT_TIE, "same": VERDICT_TIE,
    "draw": VERDICT_TIE, "neither": VERDICT_TIE, "tied": VERDICT_TIE,
}

_TRUE_STRINGS = {"true", "yes", "1", "swapped", "ba", "b_first"}
_FALSE_STRINGS = {"false", "no", "0", "original", "ab", "a_first"}


class MappingError(ValueError):
    """Raised for a malformed ``--map`` specification."""


@dataclass(frozen=True)
class Record:
    """One normalized pairwise comparison from a judge log."""

    verdict: str                       # "a" | "b" | "tie"
    human: Optional[str] = None        # same domain, or None if unlabeled
    judge: Optional[str] = None        # judge model name as logged
    model_a: Optional[str] = None
    model_b: Optional[str] = None
    len_a: Optional[int] = None        # characters or tokens; unit-agnostic
    len_b: Optional[int] = None
    pair_id: Optional[str] = None      # links swapped duplicates of one prompt
    swapped: Optional[bool] = None     # True if this row is the B-first order
    line: int = 0                      # 1-based source line, for messages

    @property
    def decisive(self) -> bool:
        return self.verdict != VERDICT_TIE

    def winner_model(self) -> Optional[str]:
        """Name of the model the judge picked, if models are known."""
        if self.verdict == VERDICT_A:
            return self.model_a
        if self.verdict == VERDICT_B:
            return self.model_b
        return None


@dataclass(frozen=True)
class Issue:
    """A per-line problem found while loading (skip or degrade, never crash)."""

    line: int
    message: str
    fatal: bool = True  # fatal issues drop the record; non-fatal drop a field

    def __str__(self) -> str:
        kind = "error" if self.fatal else "warning"
        return f"line {self.line}: {kind}: {self.message}"


@dataclass
class LoadResult:
    records: List[Record] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    n_rows: int = 0

    @property
    def n_skipped(self) -> int:
        return len({i.line for i in self.issues if i.fatal})


def parse_mapping(specs: List[str]) -> Dict[str, str]:
    """Parse repeated ``--map field=sourcekey`` options into a dict."""
    mapping: Dict[str, str] = {}
    for spec in specs:
        fieldname, sep, key = spec.partition("=")
        fieldname = fieldname.strip()
        key = key.strip()
        if not sep or not fieldname or not key:
            raise MappingError(f"--map expects field=key, got {spec!r}")
        if fieldname not in FIELD_ALIASES:
            known = ", ".join(sorted(FIELD_ALIASES))
            raise MappingError(f"unknown field {fieldname!r} in --map (known: {known})")
        mapping[fieldname] = key
    return mapping


def _lookup(obj: Dict[str, Any], fieldname: str, mapping: Dict[str, str]) -> Any:
    """Fetch a canonical field from a raw object, honoring --map overrides."""
    if fieldname in mapping:
        return obj.get(mapping[fieldname])
    for key in FIELD_ALIASES[fieldname]:
        if key in obj:
            return obj[key]
    return None


def normalize_verdict(value: Any, model_a: Optional[str], model_b: Optional[str]) -> Optional[str]:
    """Fold a raw verdict value to a/b/tie, or None if unrecognized.

    A verdict equal to one of the side model names (e.g. ``"winner":
    "nimbus-9"``) resolves to that side — common in arena-style exports.
    """
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        return None
    if isinstance(value, int):
        return {1: VERDICT_A, 2: VERDICT_B}.get(value)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text in _VERDICT_VALUES:
        return _VERDICT_VALUES[text]
    if model_a is not None and text == model_a.strip().lower():
        return VERDICT_A
    if model_b is not None and text == model_b.strip().lower():
        return VERDICT_B
    return None


def _normalize_swapped(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_STRINGS:
            return True
        if text in _FALSE_STRINGS:
            return False
    return None


def _side(obj: Dict[str, Any], side: str, mapping: Dict[str, str]) -> Tuple[Optional[str], Optional[int]]:
    """Extract (model, length) for side "a" or "b".

    The text field may be a plain string (length = character count) or a
    nested object like ``{"model": "nimbus-9", "text": "...", "tokens": 41}``.
    An explicit length field always beats a length derived from text.
    """
    model: Optional[str] = None
    length: Optional[int] = None

    raw_model = _lookup(obj, f"model_{side}", mapping)
    if isinstance(raw_model, str) and raw_model.strip():
        model = raw_model.strip()

    raw_text = _lookup(obj, f"text_{side}", mapping)
    if isinstance(raw_text, str):
        length = len(raw_text)
    elif isinstance(raw_text, dict):
        for key in ("model", "name"):
            nested = raw_text.get(key)
            if model is None and isinstance(nested, str) and nested.strip():
                model = nested.strip()
        for key in ("len", "length", "tokens", "n_tokens"):
            nested = raw_text.get(key)
            if isinstance(nested, (int, float)) and not isinstance(nested, bool):
                length = int(nested)
                break
        else:
            for key in ("text", "content", "answer", "output"):
                nested = raw_text.get(key)
                if isinstance(nested, str):
                    length = len(nested)
                    break

    raw_len = _lookup(obj, f"len_{side}", mapping)
    if isinstance(raw_len, (int, float)) and not isinstance(raw_len, bool):
        length = int(raw_len)

    if length is not None and length < 0:
        raise ValueError(f"negative length for side {side}")
    return model, length


def parse_record(obj: Any, line: int, mapping: Dict[str, str]) -> Tuple[Optional[Record], List[Issue]]:
    """Normalize one raw log object. Returns (record_or_None, issues)."""
    issues: List[Issue] = []
    if not isinstance(obj, dict):
        return None, [Issue(line, f"expected a JSON object, got {type(obj).__name__}")]

    try:
        model_a, len_a = _side(obj, "a", mapping)
        model_b, len_b = _side(obj, "b", mapping)
    except ValueError as exc:
        return None, [Issue(line, str(exc))]

    raw_verdict = _lookup(obj, "verdict", mapping)
    if raw_verdict is None:
        return None, [Issue(line, "no verdict field found (use --map verdict=<key>)")]
    verdict = normalize_verdict(raw_verdict, model_a, model_b)
    if verdict is None:
        return None, [Issue(line, f"unrecognized verdict value {raw_verdict!r}")]

    human: Optional[str] = None
    raw_human = _lookup(obj, "human", mapping)
    if raw_human is not None:
        human = normalize_verdict(raw_human, model_a, model_b)
        if human is None:
            # Keep the record: it still counts for bias stats, just not kappa.
            issues.append(Issue(line, f"unrecognized human label {raw_human!r}; treated as unlabeled", fatal=False))

    swapped: Optional[bool] = None
    raw_swapped = _lookup(obj, "swapped", mapping)
    if raw_swapped is not None:
        swapped = _normalize_swapped(raw_swapped)
        if swapped is None:
            issues.append(Issue(line, f"unrecognized swapped value {raw_swapped!r}; ignored", fatal=False))

    raw_judge = _lookup(obj, "judge", mapping)
    judge = raw_judge.strip() if isinstance(raw_judge, str) and raw_judge.strip() else None

    raw_pair = _lookup(obj, "pair_id", mapping)
    pair_id = str(raw_pair) if isinstance(raw_pair, (str, int)) and str(raw_pair).strip() else None

    record = Record(
        verdict=verdict, human=human, judge=judge,
        model_a=model_a, model_b=model_b, len_a=len_a, len_b=len_b,
        pair_id=pair_id, swapped=swapped, line=line,
    )
    return record, issues


def load_text(text: str, mapping: Optional[Dict[str, str]] = None) -> LoadResult:
    """Parse a log from an in-memory string (JSONL or a JSON array)."""
    mapping = mapping or {}
    result = LoadResult()
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            result.issues.append(Issue(1, f"invalid JSON array: {exc.msg}"))
            return result
        for index, obj in enumerate(data, start=1):
            result.n_rows += 1
            record, issues = parse_record(obj, index, mapping)
            result.issues.extend(issues)
            if record is not None:
                result.records.append(record)
        return result

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        result.n_rows += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            result.issues.append(Issue(lineno, f"invalid JSON: {exc.msg}"))
            continue
        record, issues = parse_record(obj, lineno, mapping)
        result.issues.extend(issues)
        if record is not None:
            result.records.append(record)
    return result


def load_path(path: str, mapping: Optional[Dict[str, str]] = None) -> LoadResult:
    """Load a judge log from disk. UTF-8 with BOM tolerated."""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return load_text(handle.read(), mapping)


def filter_judge(records: List[Record], judge: str) -> List[Record]:
    """Keep only records from one judge (case-insensitive exact match)."""
    wanted = judge.strip().lower()
    return [r for r in records if r.judge is not None and r.judge.lower() == wanted]
