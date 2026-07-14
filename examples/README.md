# judgecal examples

## `generate_demo_log.py`

Generates a deterministic synthetic judge log (`seed=7`, 240 rows) in which
the judge `aurora-8b`:

- mostly follows the simulated human labels (kappa lands in the "moderate" band),
- drifts to the **first position** on ~20% of rows,
- drifts to the **longer answer** on ~18% of rows,
- drifts to **its own model** on ~30% of the rows where it is a candidate.

The first 80 prompts are judged in both orders (`swapped` duplicates sharing a
`pair_id`), which feeds the swap-consistency analysis.

```bash
python examples/generate_demo_log.py demo-log.jsonl
judgecal audit demo-log.jsonl
```

Because the generator is seeded, the audit output is fully reproducible; the
README quickstart and `scripts/smoke.sh` both assert on it.

## `sample-log.jsonl`

A tiny handcrafted 12-row log using the canonical field names, small enough to
read in one screen. Useful as a schema reference and for trying subcommands:

```bash
judgecal validate examples/sample-log.jsonl
judgecal position examples/sample-log.jsonl
```

See [`docs/log-format.md`](../docs/log-format.md) for the full field and alias
reference.
