"""Human agreement: does the judge track your human labels at all?

Raw percent agreement is flattered by class imbalance (a judge that always
says "a" agrees with humans 60% of the time if humans pick "a" 60% of the
time), so the headline number is Cohen's kappa over the three-way
a/b/tie decision, with the raw numbers and the full confusion matrix kept
alongside as receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .records import Record, VERDICTS
from .stats import cohen_kappa, confusion_matrix, kappa_band, proportion, round_opt


@dataclass
class AgreementResult:
    n_labeled: int                      # records carrying a human label
    observed_agreement: Optional[float]  # raw agreement over all labeled rows
    kappa: Optional[float]
    band: Optional[str]                 # Landis & Koch interpretation
    confusion: Dict[str, Dict[str, int]]  # judge verdict -> human label -> n
    n_decisive_both: int                # rows where judge AND human were decisive
    decisive_agreement: Optional[float]  # agreement restricted to those rows
    judge_tie_rate: Optional[float]
    human_tie_rate: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_labeled": self.n_labeled,
            "observed_agreement": round_opt(self.observed_agreement),
            "kappa": round_opt(self.kappa),
            "band": self.band,
            "confusion": self.confusion,
            "n_decisive_both": self.n_decisive_both,
            "decisive_agreement": round_opt(self.decisive_agreement),
            "judge_tie_rate": round_opt(self.judge_tie_rate),
            "human_tie_rate": round_opt(self.human_tie_rate),
        }


def analyze_agreement(records: List[Record]) -> AgreementResult:
    """Compare judge verdicts against human labels wherever both exist."""
    pairs = [(r.verdict, r.human) for r in records if r.human is not None]
    n = len(pairs)

    kappa = cohen_kappa(pairs) if n else None
    agree = sum(1 for j, h in pairs if j == h)

    decisive = [(j, h) for j, h in pairs if j != "tie" and h != "tie"]
    decisive_agree = sum(1 for j, h in decisive if j == h)

    judge_ties = sum(1 for j, _ in pairs if j == "tie")
    human_ties = sum(1 for _, h in pairs if h == "tie")

    return AgreementResult(
        n_labeled=n,
        observed_agreement=proportion(agree, n),
        kappa=kappa,
        band=kappa_band(kappa) if kappa is not None else None,
        confusion=confusion_matrix(pairs, VERDICTS),
        n_decisive_both=len(decisive),
        decisive_agreement=proportion(decisive_agree, len(decisive)),
        judge_tie_rate=proportion(judge_ties, n),
        human_tie_rate=proportion(human_ties, n),
    )
