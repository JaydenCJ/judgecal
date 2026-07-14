# Contributing to judgecal

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

judgecal needs Python ≥ 3.9 and nothing else at runtime.

```bash
git clone https://github.com/JaydenCJ/judgecal
cd judgecal
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 95 unit + CLI tests, fully offline
bash scripts/smoke.sh  # end-to-end: generate demo log, audit, gates, validate
```

Both must pass before a pull request is reviewed; `scripts/smoke.sh` exercises
the real CLI on a generated log and must print `SMOKE OK`. The whole
verification story is local — this repository intentionally ships no CI.

## Before you open a pull request

1. Keep formatting consistent with the surrounding code (PEP 8, 4-space indent).
2. `pytest` must pass with zero failures.
3. `bash scripts/smoke.sh` must print `SMOKE OK`.
4. Add tests for behavior changes; keep the statistics in pure, unit-testable
   functions (`stats.py` has no I/O for a reason).
5. Statistical claims need a source: cite the formula or a worked example in
   the docstring, and pin an exact value in a test where possible.

## Ground rules

- **No runtime dependencies, ever.** The standard library is the whole
  toolbox; test-only dependencies belong in the `dev` extra.
- **judgecal never calls a model.** No network I/O anywhere in the package —
  it reads a local log file and prints. This is the product's core promise.
- **Schema changes need a version bump.** Anything that changes the meaning of
  a field in the JSON report must bump `SCHEMA_VERSION` and update the README
  in the same pull request.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` are line-for-line parallel; update all three together
  (English is authoritative).
- Code comments and doc comments are written in English.

## Reporting bugs

Please include `judgecal --version` output, the exact command line, and a
minimal log snippet that reproduces the problem (a handful of JSONL rows is
usually enough — redact response text freely, judgecal only needs the
structure).

## Security

judgecal parses untrusted log files, so parser robustness reports are
security-relevant. Please do not open public issues for vulnerabilities; use
GitHub's private vulnerability reporting on this repository instead.
