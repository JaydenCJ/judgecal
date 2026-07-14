"""The shipped example generator feeds a full audit, deterministically.

This is the same path scripts/smoke.sh and the README quickstart use, so a
regression here means the documented demo is broken.
"""

import json
import runpy
import sys
from pathlib import Path

from judgecal.cli import main
from judgecal.records import load_path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = str(ROOT / "examples" / "generate_demo_log.py")
SAMPLE = str(ROOT / "examples" / "sample-log.jsonl")


def _generate(tmp_path, monkeypatch, name="demo.jsonl"):
    out = tmp_path / name
    monkeypatch.setattr(sys, "argv", [EXAMPLE, str(out)])
    try:
        runpy.run_path(EXAMPLE, run_name="__main__")
    except SystemExit as exc:  # the script exits 0 on success
        assert exc.code == 0
    return str(out)


def test_generator_is_deterministic(tmp_path, monkeypatch):
    path1 = _generate(tmp_path, monkeypatch, "one.jsonl")
    path2 = _generate(tmp_path, monkeypatch, "two.jsonl")
    with open(path1, encoding="utf-8") as f1, open(path2, encoding="utf-8") as f2:
        assert f1.read() == f2.read()


def test_generator_output_parses_cleanly(tmp_path, monkeypatch):
    path = _generate(tmp_path, monkeypatch)
    result = load_path(path)
    assert result.n_rows == 240
    assert len(result.records) == 240
    assert result.issues == []


def test_audit_detects_all_three_planted_biases(tmp_path, monkeypatch, capsys):
    path = _generate(tmp_path, monkeypatch)
    capsys.readouterr()  # drop the generator's own stdout
    assert main(["audit", path, "--format", "json"]) == 0
    audit = json.loads(capsys.readouterr().out)
    # Position: the generator drifts to slot A on ~20% of rows.
    assert audit["position"]["first_win_rate"] > 0.55
    assert audit["position"]["p_value"] < 0.05
    # Length: the judge rewards length more than the simulated humans do.
    assert audit["length"]["human_adjusted"]["adjusted_delta"] > 0.05
    # Self-preference: aurora-8b judges itself favorably beyond quality.
    assert audit["self_preference"]["human_adjusted"]["adjusted_delta"] > 0.05
    assert audit["overview"]["worst_finding"] == "FLAG"


def test_sample_log_audit_runs_end_to_end(capsys):
    # The tiny handcrafted log in examples/ must stay valid too.
    assert main(["validate", SAMPLE]) == 0
    capsys.readouterr()
    assert main(["audit", SAMPLE]) == 0
    out = capsys.readouterr().out
    assert "parsed: 12" in out
