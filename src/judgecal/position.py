"""Position bias: does the judge favor whichever answer comes first?

Two complementary measurements:

1. **First-slot win rate** over all decisive verdicts, tested against the
   50% you'd expect from an order-blind judge (exact two-sided binomial).
   This is meaningful when the log's A/B assignment is randomized — which is
   exactly what swapped duplicates guarantee.
2. **Swap consistency** over pairs of rows that judge the *same* prompt in
   both orders (linked by ``pair_id``). An order-blind judge picks the same
   model both times; a position-biased one sticks to a slot. This isolates
   position bias from model quality entirely.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .records import Record, VERDICT_A, VERDICT_B, VERDICT_TIE
from .stats import binom_two_sided, proportion, round_opt, wilson_interval


@dataclass
class PositionResult:
    n_decisive: int
    first_wins: int
    first_win_rate: Optional[float]
    delta: Optional[float]              # |rate - 0.5|, the gateable number
    ci_low: Optional[float]
    ci_high: Optional[float]
    p_value: Optional[float]
    n_ties: int
    # Swap-pair analysis (None-ish when the log has no linked duplicates):
    n_pairs: int
    consistent: int                     # same winning model (or tie) both orders
    first_sticky: int                   # picked slot A in both orders
    second_sticky: int                  # picked slot B in both orders
    mixed: int                          # tie in one order, decisive in the other
    consistency_rate: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_decisive": self.n_decisive,
            "first_wins": self.first_wins,
            "first_win_rate": round_opt(self.first_win_rate),
            "delta": round_opt(self.delta),
            "ci_low": round_opt(self.ci_low),
            "ci_high": round_opt(self.ci_high),
            "p_value": round_opt(self.p_value, 6),
            "n_ties": self.n_ties,
            "swap_pairs": {
                "n_pairs": self.n_pairs,
                "consistent": self.consistent,
                "first_sticky": self.first_sticky,
                "second_sticky": self.second_sticky,
                "mixed": self.mixed,
                "consistency_rate": round_opt(self.consistency_rate),
            },
        }


def _is_swap_mate(r1: Record, r2: Record) -> bool:
    """True when r2 judges the same prompt as r1 with the sides exchanged."""
    if r1.model_a and r1.model_b and r2.model_a and r2.model_b:
        return r1.model_a == r2.model_b and r1.model_b == r2.model_a
    if r1.swapped is not None and r2.swapped is not None:
        return r1.swapped != r2.swapped
    return False


def _pair_swaps(records: List[Record]) -> List[Tuple[Record, Record]]:
    """Greedily match swap-mates inside each pair_id group, in file order.

    Greedy first-match keeps the pairing deterministic and handles groups
    that hold more than two rows (e.g. a prompt judged twice in each order).
    """
    groups: Dict[str, List[Record]] = defaultdict(list)
    for record in records:
        if record.pair_id is not None:
            groups[record.pair_id].append(record)

    pairs: List[Tuple[Record, Record]] = []
    for pair_id in sorted(groups):
        group = groups[pair_id]
        used = [False] * len(group)
        for i, first in enumerate(group):
            if used[i]:
                continue
            for j in range(i + 1, len(group)):
                if used[j]:
                    continue
                if _is_swap_mate(first, group[j]):
                    used[i] = used[j] = True
                    pairs.append((first, group[j]))
                    break
    return pairs


def _classify_pair(r1: Record, r2: Record) -> str:
    """Classify one swap pair: consistent / first_sticky / second_sticky / mixed.

    With models known we compare winning model names; without them the swapped
    flag tells us the orders differ, so "consistent" means the verdicts flip.
    Either way, both-"a" means the judge chased slot A and both-"b" slot B.
    """
    v1, v2 = r1.verdict, r2.verdict
    if v1 == VERDICT_TIE and v2 == VERDICT_TIE:
        return "consistent"
    if v1 == VERDICT_TIE or v2 == VERDICT_TIE:
        return "mixed"
    if v1 == VERDICT_A and v2 == VERDICT_A:
        return "first_sticky"
    if v1 == VERDICT_B and v2 == VERDICT_B:
        return "second_sticky"
    # Verdicts flipped (a/b or b/a): with the sides exchanged, that is the
    # same underlying model winning both times.
    return "consistent"


def analyze_position(records: List[Record]) -> PositionResult:
    decisive = [r for r in records if r.decisive]
    n = len(decisive)
    first_wins = sum(1 for r in decisive if r.verdict == VERDICT_A)
    rate = proportion(first_wins, n)
    ci = wilson_interval(first_wins, n) if n else (None, None)
    p_value = binom_two_sided(first_wins, n) if n else None

    counts = {"consistent": 0, "first_sticky": 0, "second_sticky": 0, "mixed": 0}
    pairs = _pair_swaps(records)
    for r1, r2 in pairs:
        counts[_classify_pair(r1, r2)] += 1

    return PositionResult(
        n_decisive=n,
        first_wins=first_wins,
        first_win_rate=rate,
        delta=abs(rate - 0.5) if rate is not None else None,
        ci_low=ci[0],
        ci_high=ci[1],
        p_value=p_value,
        n_ties=len(records) - n,
        n_pairs=len(pairs),
        consistent=counts["consistent"],
        first_sticky=counts["first_sticky"],
        second_sticky=counts["second_sticky"],
        mixed=counts["mixed"],
        consistency_rate=proportion(counts["consistent"], len(pairs)),
    )
