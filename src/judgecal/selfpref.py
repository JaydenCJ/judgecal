"""Self-preference: does the judge favor outputs from its own model family?

The raw self-win rate is confounded by quality — a strong judge model may
legitimately produce strong answers. As with length bias, the fix is human
labels on the same rows: if the judge picks its own side 68% of the time but
your humans pick that side 61% of the time, the self-preference is 7 points,
not 18. judgecal reports both and flags on the adjusted number when it can.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .records import Record, VERDICT_A, VERDICT_B
from .stats import binom_two_sided, proportion, round_opt, wilson_interval

_SEPARATORS = re.compile(r"[\s_/.:]+")


def normalize_model(name: str) -> str:
    """Canonical form for model-name comparison: lowercase, one separator."""
    return _SEPARATORS.sub("-", name.strip().lower()).strip("-")


def same_family(judge: str, model: str) -> bool:
    """Family match: equal after normalization, or one extends the other.

    ``judge-x`` matches ``judge-x-mini`` and ``judge_x`` but not ``judge-xl``
    (the extension must start at a separator boundary).
    """
    a, b = normalize_model(judge), normalize_model(model)
    if not a or not b:
        return False
    return a == b or a.startswith(b + "-") or b.startswith(a + "-")


def _self_side(record: Record, family: bool) -> Optional[str]:
    """Which side is the judge's own model? None if neither or both are.

    Both-sides-self rows carry no self-preference signal, so they are
    excluded rather than counted as half a win.
    """
    if record.judge is None or record.model_a is None or record.model_b is None:
        return None
    if family:
        a_is_self = same_family(record.judge, record.model_a)
        b_is_self = same_family(record.judge, record.model_b)
    else:
        norm = normalize_model(record.judge)
        a_is_self = normalize_model(record.model_a) == norm
        b_is_self = normalize_model(record.model_b) == norm
    if a_is_self == b_is_self:
        return None
    return VERDICT_A if a_is_self else VERDICT_B


@dataclass
class SelfPreferenceResult:
    n_self: int                        # rows with exactly one self side, decisive
    self_wins: int
    self_win_rate: Optional[float]
    delta: Optional[float]             # |rate - 0.5| (quality-confounded)
    ci_low: Optional[float]
    ci_high: Optional[float]
    p_value: Optional[float]
    n_ties: int
    judges_matched: List[str] = field(default_factory=list)
    # Human-adjusted view on rows where both judge and human are decisive:
    n_human: int = 0
    judge_self_rate_h: Optional[float] = None
    human_self_rate: Optional[float] = None
    adjusted_delta: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_self": self.n_self,
            "self_wins": self.self_wins,
            "self_win_rate": round_opt(self.self_win_rate),
            "delta": round_opt(self.delta),
            "ci_low": round_opt(self.ci_low),
            "ci_high": round_opt(self.ci_high),
            "p_value": round_opt(self.p_value, 6),
            "n_ties": self.n_ties,
            "judges_matched": self.judges_matched,
            "human_adjusted": {
                "n": self.n_human,
                "judge_self_rate": round_opt(self.judge_self_rate_h),
                "human_self_rate": round_opt(self.human_self_rate),
                "adjusted_delta": round_opt(self.adjusted_delta),
            },
        }


def analyze_self_preference(records: List[Record], family: bool = True) -> SelfPreferenceResult:
    sided = [(r, _self_side(r, family)) for r in records]
    eligible = [(r, s) for r, s in sided if s is not None]
    decisive = [(r, s) for r, s in eligible if r.decisive]
    n_ties = len(eligible) - len(decisive)

    n = len(decisive)
    self_wins = sum(1 for r, s in decisive if r.verdict == s)
    rate = proportion(self_wins, n)
    ci = wilson_interval(self_wins, n) if n else (None, None)
    p_value = binom_two_sided(self_wins, n) if n else None

    judges = sorted({r.judge for r, _ in eligible if r.judge is not None})

    shared = [(r, s) for r, s in decisive if r.human in (VERDICT_A, VERDICT_B)]
    n_human = len(shared)
    judge_h = proportion(sum(1 for r, s in shared if r.verdict == s), n_human)
    human_h = proportion(sum(1 for r, s in shared if r.human == s), n_human)
    adjusted = (judge_h - human_h) if judge_h is not None and human_h is not None else None

    return SelfPreferenceResult(
        n_self=n,
        self_wins=self_wins,
        self_win_rate=rate,
        delta=abs(rate - 0.5) if rate is not None else None,
        ci_low=ci[0],
        ci_high=ci[1],
        p_value=p_value,
        n_ties=n_ties,
        judges_matched=judges,
        n_human=n_human,
        judge_self_rate_h=judge_h,
        human_self_rate=human_h,
        adjusted_delta=adjusted,
    )
