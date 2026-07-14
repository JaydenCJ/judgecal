"""End-to-end CLI behavior through main(), including exit codes.

These tests call judgecal.cli.main() in-process with capsys — the same code
path as the installed console script, without subprocess overhead.
"""

import json
import subprocess
import sys

import pytest

from judgecal import __version__
from judgecal.cli import main


def _rows_biased(n=40):
    rows = []
    for i in range(n):
        rows.append({
            "verdict": "a" if i % 4 != 3 else "b",
            "human": "a" if i % 2 == 0 else "b",
            "judge": "j1", "model_a": "j1", "model_b": "m2",
            "len_a": 100 + i, "len_b": 90, "pair_id": f"q{i}",
        })
    return rows


def test_version_flag_and_module_entrypoint(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"judgecal {__version__}"
    # ``python -m judgecal`` wires the exact same callable.
    import judgecal.__main__ as dunder
    assert dunder.main is main


def test_audit_text_report_and_exit_zero(write_jsonl, capsys):
    path = write_jsonl(_rows_biased())
    assert main(["audit", path]) == 0
    out = capsys.readouterr().out
    assert "[agreement]" in out and "[position]" in out
    assert "overall:" in out


def test_audit_json_format_round_trips(write_jsonl, capsys):
    path = write_jsonl(_rows_biased())
    assert main(["audit", path, "--format", "json"]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["schema_version"] == 1
    assert audit["overview"]["n_parsed"] == 40


def test_audit_markdown_format(write_jsonl, capsys):
    path = write_jsonl(_rows_biased())
    assert main(["audit", path, "--format", "markdown"]) == 0
    assert "| Check | Headline | n | Verdict |" in capsys.readouterr().out


def test_section_commands_print_only_their_section(write_jsonl, capsys):
    path = write_jsonl(_rows_biased())
    assert main(["length", path]) == 0
    out = capsys.readouterr().out
    assert "[length]" in out and "[agreement]" not in out


def test_gate_exit_codes_and_stderr_reason(write_jsonl, capsys):
    path = write_jsonl(_rows_biased(80))
    assert main(["audit", path, "--max-position-delta", "0.01"]) == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err and "--max-position-delta" in captured.err
    assert main(["audit", path, "--min-kappa", "0.1", "--max-self-delta", "0.9"]) == 0


def test_map_option_reaches_the_loader(write_jsonl, capsys):
    rows = [{"my_verdict": "a", "judge": "j1"} for _ in range(3)]
    path = write_jsonl(rows)
    assert main(["audit", path, "--map", "verdict=my_verdict"]) == 0
    assert "parsed: 3" in capsys.readouterr().out


def test_usage_errors_exit_two(write_jsonl, capsys):
    path = write_jsonl(_rows_biased(3))
    assert main(["audit", path, "--map", "bogus=field"]) == 2
    assert "unknown field" in capsys.readouterr().err
    assert main(["audit", "/nonexistent/log.jsonl"]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_judge_filter_that_matches_nothing_exits_two(write_jsonl, capsys):
    path = write_jsonl(_rows_biased(5))
    assert main(["audit", path, "--judge", "other-judge"]) == 2
    assert "no usable records" in capsys.readouterr().err


def test_validate_clean_log_exits_zero(write_jsonl, capsys):
    path = write_jsonl(_rows_biased(5))
    assert main(["validate", path]) == 0
    assert "5 valid, 0 skipped" in capsys.readouterr().out


def test_validate_broken_log_exits_one_and_names_lines(tmp_path, capsys):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"verdict": "a"}\n{oops\n{"verdict": "??"}\n', encoding="utf-8")
    assert main(["validate", str(path)]) == 1
    out = capsys.readouterr().out
    assert "line 2" in out and "line 3" in out
    assert "1 valid, 2 skipped" in out


def test_validate_summary_uses_singular_forms(write_jsonl, capsys):
    # "1 rows ... 1 warnings" reads like a bug; counts of one must be singular.
    path = write_jsonl([{"verdict": "a", "human": "??"}])
    assert main(["validate", path]) == 0
    assert "1 row: 1 valid, 0 skipped, 1 warning" in capsys.readouterr().out


def test_exact_self_flag_changes_matching(write_jsonl, capsys):
    rows = [{"verdict": "a", "judge": "j1", "model_a": "j1-mini", "model_b": "m2"}
            for _ in range(12)]
    path = write_jsonl(rows)
    main(["self", path, "--format", "json"])
    family_n = json.loads(capsys.readouterr().out)["self_preference"]["n_self"]
    main(["self", path, "--exact-self", "--format", "json"])
    exact_n = json.loads(capsys.readouterr().out)["self_preference"]["n_self"]
    assert family_n == 12 and exact_n == 0


def test_closed_stdout_pipe_exits_zero_and_quiet(write_jsonl):
    # `judgecal audit log | head -1` closes stdout mid-report; that must not
    # surface as a bogus "cannot read <file>" error (regression: the OSError
    # handler used to swallow BrokenPipeError). Needs a real pipe, hence a
    # subprocess rather than capsys.
    path = write_jsonl(_rows_biased())
    proc = subprocess.Popen(
        [sys.executable, "-m", "judgecal", "audit", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    proc.stdout.readline()   # take one line, then hang up
    proc.stdout.close()
    stderr = proc.stderr.read()
    proc.stderr.close()
    assert proc.wait() == 0
    assert stderr == b""


def test_min_n_option_threads_through(write_jsonl, capsys):
    rows = [{"verdict": "a", "human": "a"} for _ in range(4)]
    path = write_jsonl(rows)
    main(["agreement", path, "--min-n", "3"])
    assert "NO DATA" not in capsys.readouterr().out
    main(["agreement", path, "--min-n", "5"])
    assert "NO DATA" in capsys.readouterr().out
