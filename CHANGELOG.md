# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- JSONL / JSON-array log loader with a canonical pairwise schema, an alias
  table for common export field names, `--map field=key` overrides, verdict
  spelling normalization (including model-name verdicts), and line-numbered
  skip/degrade issue reporting (`records.py`).
- Standard-library statistics core: Cohen's kappa (three-way a/b/tie),
  exact two-sided binomial test (log-space, stable for large n), Wilson 95%
  confidence intervals, and Pearson correlation (`stats.py`).
- Human-agreement analysis: observed agreement, kappa with Landis & Koch
  bands, decisive-only agreement, per-rater tie rates, and a full judge-vs-
  human confusion matrix.
- Position-bias analysis: first-slot win rate with CI and exact p-value, plus
  swap-pair consistency over `pair_id`-linked reversed duplicates
  (consistent / first-sticky / second-sticky / mixed).
- Length-bias analysis: longer-answer win rate, log-length-ratio correlation,
  ratio-bucket breakdown, and a human-adjusted delta that nets out quality.
- Self-preference analysis: model-family name matching (`--exact-self` to
  disable), own-side win rate, and a human-adjusted self-preference delta.
- OK / WARN / FLAG findings with documented default thresholds, and CI gates
  (`--min-kappa`, `--max-position-delta`, `--max-length-delta`,
  `--max-self-delta`) that exit 1 — and fail closed when a gated metric
  cannot be measured.
- `judgecal` CLI: `audit`, `agreement`, `position`, `length`, `self`,
  `validate`; text, JSON (`schema_version: 1`, sorted keys), and Markdown
  output; `--judge` filter and `--min-n` floor.
- Deterministic demo-log generator and a handcrafted sample log in
  `examples/`, plus the log-format reference in `docs/log-format.md`.
- 95 offline deterministic tests and `scripts/smoke.sh` (prints `SMOKE OK`).

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/judgecal/releases/tag/v0.1.0
