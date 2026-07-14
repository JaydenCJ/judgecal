#!/usr/bin/env python3
"""Generate a deterministic synthetic judge log with three planted biases.

The simulated judge ("aurora-8b", which is also one of the candidate models):

* follows the human label most of the time (so kappa lands around "moderate"),
* drifts toward the FIRST position on a fixed fraction of rows,
* drifts toward the LONGER answer on another fixed fraction,
* drifts toward ITS OWN model on rows where aurora-8b is a candidate.

Because the generator is seeded, ``judgecal audit`` over the output is fully
reproducible — the README quickstart and scripts/smoke.sh both rely on that.

Usage: python examples/generate_demo_log.py [OUT.jsonl]
"""

from __future__ import annotations

import json
import random
import sys

SEED = 7
N_PROMPTS = 160          # each prompt judged in the original order...
N_SWAPPED = 80           # ...and the first N_SWAPPED also in swapped order
JUDGE = "aurora-8b"

# Candidate models with a latent quality score; aurora-8b is mid-pack so its
# self-preference cannot be explained away by quality.
MODELS = {"aurora-8b": 0.62, "nimbus-9": 0.70, "cobalt-1": 0.55, "petrel-3": 0.48}

P_POSITION_DRIFT = 0.20  # chance the judge just takes whatever is first
P_SELF_DRIFT = 0.30      # chance the judge takes its own answer if present
P_LENGTH_DRIFT = 0.18    # chance the judge takes the longer answer
P_JUDGE_NOISE = 0.08     # residual random disagreement with the human label
P_HUMAN_TIE = 0.10


def human_label(rng: random.Random, quality_a: float, quality_b: float) -> str:
    """Ground truth: mostly quality-driven, with occasional genuine ties."""
    if rng.random() < P_HUMAN_TIE:
        return "tie"
    edge = quality_a - quality_b + rng.gauss(0, 0.08)
    return "a" if edge > 0 else "b"


def judge_verdict(rng: random.Random, human: str, model_a: str, model_b: str,
                  len_a: int, len_b: int) -> str:
    """The biased judge: bias hooks fire first, then noisy human-following."""
    if rng.random() < P_POSITION_DRIFT:
        return "a"
    if JUDGE in (model_a, model_b) and rng.random() < P_SELF_DRIFT:
        return "a" if model_a == JUDGE else "b"
    if rng.random() < P_LENGTH_DRIFT:
        return "a" if len_a > len_b else "b"
    if rng.random() < P_JUDGE_NOISE:
        return rng.choice(["a", "b", "tie"])
    return human


def flip(verdict: str) -> str:
    return {"a": "b", "b": "a", "tie": "tie"}[verdict]


def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "demo-log.jsonl"
    rng = random.Random(SEED)
    names = sorted(MODELS)
    rows = []

    for i in range(N_PROMPTS):
        model_a, model_b = rng.sample(names, 2)
        len_a = rng.randint(220, 1400)
        len_b = rng.randint(220, 1400)
        human = human_label(rng, MODELS[model_a], MODELS[model_b])
        verdict = judge_verdict(rng, human, model_a, model_b, len_a, len_b)
        rows.append({
            "pair_id": f"q{i:03d}", "judge": JUDGE, "swapped": False,
            "model_a": model_a, "model_b": model_b,
            "len_a": len_a, "len_b": len_b,
            "verdict": verdict, "human": human,
        })
        if i < N_SWAPPED:
            # Same prompt, sides exchanged; the judge decides again with the
            # same bias hooks, so position-locked verdicts show up as
            # first-sticky pairs in the swap analysis.
            verdict_s = judge_verdict(rng, flip(human), model_b, model_a, len_b, len_a)
            rows.append({
                "pair_id": f"q{i:03d}", "judge": JUDGE, "swapped": True,
                "model_a": model_b, "model_b": model_a,
                "len_a": len_b, "len_b": len_a,
                "verdict": verdict_s, "human": flip(human),
            })

    with open(out_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} records to {out_path} (seed={SEED}, judge={JUDGE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
