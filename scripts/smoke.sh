#!/usr/bin/env bash
# Smoke test for judgecal: generate the deterministic demo log, audit it in
# all three formats, check the CI gates fail loudly, and validate a broken log.
# Self-contained: pure stdlib, no network, idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# The package has zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/judgecal-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. Generate the seeded demo log (240 rows, three planted biases).
gen_out="$("$PYTHON" "$ROOT/examples/generate_demo_log.py" "$WORKDIR/demo.jsonl")" \
  || fail "generate_demo_log.py exited non-zero"
echo "$gen_out" | sed 's/^/[gen] /'
echo "$gen_out" | grep -q "wrote 240 records" || fail "generator did not write 240 records"

# 2. validate: the generated log must parse cleanly.
val_out="$("$PYTHON" -m judgecal validate "$WORKDIR/demo.jsonl")" \
  || fail "validate exited non-zero on a clean log"
echo "$val_out" | grep -q "240 valid, 0 skipped" || fail "validate miscounted the clean log"

# 3. audit (text): all four sections present, planted biases surfaced.
audit_out="$("$PYTHON" -m judgecal audit "$WORKDIR/demo.jsonl")" \
  || fail "audit exited non-zero without gates"
echo "$audit_out" | sed 's/^/[audit] /'
for section in "\[agreement\]" "\[position\]" "\[length\]" "\[self\]"; do
  echo "$audit_out" | grep -q "$section" || fail "audit missing section $section"
done
echo "$audit_out" | grep -q "Cohen's kappa" || fail "audit missing kappa line"
echo "$audit_out" | grep -q "FLAG: first-position" || fail "audit did not flag the planted position bias"
echo "$audit_out" | grep -q "FLAG: judge picks its own model" || fail "audit did not flag the planted self-preference"
echo "$audit_out" | grep -q "overall: FLAG" || fail "audit overall verdict should be FLAG"

# 4. audit (json): valid JSON with the expected schema version.
"$PYTHON" -m judgecal audit "$WORKDIR/demo.jsonl" --format json > "$WORKDIR/audit.json" \
  || fail "audit --format json exited non-zero"
schema="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["schema_version"])' "$WORKDIR/audit.json")"
[ "$schema" = "1" ] || fail "unexpected schema_version: $schema"

# 5. audit (markdown): summary table renders.
"$PYTHON" -m judgecal audit "$WORKDIR/demo.jsonl" --format markdown \
  | grep -q "| Check | Headline | n | Verdict |" || fail "markdown summary table missing"

# 6. Gates: an impossible kappa bar must exit 1 with a FAIL line on stderr.
set +e
gate_err="$("$PYTHON" -m judgecal audit "$WORKDIR/demo.jsonl" --min-kappa 0.99 2>&1 >/dev/null)"
gate_rc=$?
set -e
[ "$gate_rc" -eq 1 ] || fail "gate violation should exit 1, got $gate_rc"
echo "$gate_err" | grep -q "FAIL: gate --min-kappa" || fail "gate violation not reported on stderr"

# 7. Gates: loose thresholds pass on the same log.
"$PYTHON" -m judgecal audit "$WORKDIR/demo.jsonl" --min-kappa 0.3 --max-self-delta 0.5 >/dev/null \
  || fail "loose gates should exit 0"

# 8. validate: a broken log exits 1 and names the bad lines.
printf '%s\n' '{"verdict": "a"}' '{oops' '{"verdict": "??"}' > "$WORKDIR/broken.jsonl"
set +e
broken_out="$("$PYTHON" -m judgecal validate "$WORKDIR/broken.jsonl")"
broken_rc=$?
set -e
[ "$broken_rc" -eq 1 ] || fail "validate on a broken log should exit 1, got $broken_rc"
echo "$broken_out" | grep -q "line 2" || fail "validate did not name the broken line"
echo "$broken_out" | grep -q "1 valid, 2 skipped" || fail "validate miscounted the broken log"

# 9. --version agrees with the package.
version_out="$("$PYTHON" -m judgecal --version)"
pkg_version="$("$PYTHON" -c 'import judgecal; print(judgecal.__version__)')"
[ "$version_out" = "judgecal $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
