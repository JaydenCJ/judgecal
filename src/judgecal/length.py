"""Length bias: does the judge reward the longer answer?

The naive number — how often the longer response wins — conflates verbosity
preference with genuine quality (longer answers are sometimes better). So
when human labels exist, judgecal also computes the human longer-win rate on
the *same rows* and reports the difference: how much more than your humans
the judge rewards length. That delta is the honest bias figure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .records import Record, VERDICT_A, VERDICT_B
from .stats import binom_two_sided, pearson, proportion, round_opt, wilson_interval

# Length-ratio buckets (longer/shorter), for the breakdown table. A judge that
# only favors length when the gap is huge shows up here, not in the headline.
BUCKETS: Tuple[Tuple[float, float, str], ...] = (
    (1.0, 1.1, "<=1.1x"),
    (1.1, 1.5, "1.1-1.5x"),
    (1.5, 2.0, "1.5-2x"),
    (2.0, math.inf, ">2x"),
)


@dataclass
class LengthResult:
    n_compared: int                     # decisive rows with two unequal lengths
    longer_wins: int
    longer_win_rate: Optional[float]
    delta: Optional[float]              # |rate - 0.5|
    ci_low: Optional[float]
    ci_high: Optional[float]
    p_value: Optional[float]
    correlation: Optional[float]        # log length ratio vs signed verdict
    buckets: List[Dict[str, Any]]
    # Human-adjusted view (rows where judge and human are both decisive):
    n_human: int
    judge_longer_rate_h: Optional[float]
    human_longer_rate: Optional[float]
    adjusted_delta: Optional[float]     # judge rate - human rate on shared rows

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_compared": self.n_compared,
            "longer_wins": self.longer_wins,
            "longer_win_rate": round_opt(self.longer_win_rate),
            "delta": round_opt(self.delta),
            "ci_low": round_opt(self.ci_low),
            "ci_high": round_opt(self.ci_high),
            "p_value": round_opt(self.p_value, 6),
            "correlation": round_opt(self.correlation),
            "buckets": self.buckets,
            "human_adjusted": {
                "n": self.n_human,
                "judge_longer_rate": round_opt(self.judge_longer_rate_h),
                "human_longer_rate": round_opt(self.human_longer_rate),
                "adjusted_delta": round_opt(self.adjusted_delta),
            },
        }


def _comparable(record: Record) -> bool:
    """Rows where "the longer one" is well-defined and the judge chose a side."""
    return (
        record.decisive
        and record.len_a is not None
        and record.len_b is not None
        and record.len_a > 0
        and record.len_b > 0
        and record.len_a != record.len_b
    )


def _longer_side(record: Record) -> str:
    assert record.len_a is not None and record.len_b is not None
    return VERDICT_A if record.len_a > record.len_b else VERDICT_B


def _ratio(record: Record) -> float:
    assert record.len_a is not None and record.len_b is not None
    return max(record.len_a, record.len_b) / min(record.len_a, record.len_b)


def analyze_length(records: List[Record]) -> LengthResult:
    compared = [r for r in records if _comparable(r)]
    n = len(compared)
    longer_wins = sum(1 for r in compared if r.verdict == _longer_side(r))
    rate = proportion(longer_wins, n)
    ci = wilson_interval(longer_wins, n) if n else (None, None)
    p_value = binom_two_sided(longer_wins, n) if n else None

    # Correlation: strength of the length signal, not just its direction.
    xs = [math.log(r.len_a / r.len_b) for r in compared]  # type: ignore[operator]
    ys = [1.0 if r.verdict == VERDICT_A else -1.0 for r in compared]
    correlation = pearson(xs, ys)

    buckets: List[Dict[str, Any]] = []
    for low, high, label in BUCKETS:
        rows = [r for r in compared if low < _ratio(r) <= high]
        wins = sum(1 for r in rows if r.verdict == _longer_side(r))
        buckets.append({
            "bucket": label,
            "n": len(rows),
            "longer_win_rate": round_opt(proportion(wins, len(rows))),
        })

    # Human-adjusted delta over the shared decisive subset.
    shared = [r for r in compared if r.human in (VERDICT_A, VERDICT_B)]
    n_human = len(shared)
    judge_h = proportion(sum(1 for r in shared if r.verdict == _longer_side(r)), n_human)
    human_h = proportion(sum(1 for r in shared if r.human == _longer_side(r)), n_human)
    adjusted = (judge_h - human_h) if judge_h is not None and human_h is not None else None

    return LengthResult(
        n_compared=n,
        longer_wins=longer_wins,
        longer_win_rate=rate,
        delta=abs(rate - 0.5) if rate is not None else None,
        ci_low=ci[0],
        ci_high=ci[1],
        p_value=p_value,
        correlation=correlation,
        buckets=buckets,
        n_human=n_human,
        judge_longer_rate_h=judge_h,
        human_longer_rate=human_h,
        adjusted_delta=adjusted,
    )
