"""Assemble the audit and render it as text, Markdown, or JSON.

The audit dict is the single source of truth: every renderer and every gate
reads from it, so the JSON output always contains exactly what the terminal
showed. ``schema_version`` is bumped on any breaking change to that dict.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import __version__
from .agreement import analyze_agreement
from .length import analyze_length
from .position import analyze_position
from .records import Record, VERDICTS
from .selfpref import analyze_self_preference
from .stats import proportion, round_opt

SCHEMA_VERSION = 1

# Findings levels, worst last so max() on the index works.
LEVELS = ("OK", "WARN", "FLAG", "NO DATA")

# Default thresholds behind the OK/WARN/FLAG verdicts. Documented in the
# README; gates (--min-kappa etc.) are separate and explicit.
KAPPA_WARN = 0.60       # below: WARN
KAPPA_FLAG = 0.40       # below: FLAG
POSITION_WARN = 0.05    # |first-win rate - 0.5| at p < ALPHA
POSITION_FLAG = 0.10
CONSISTENCY_WARN = 0.80  # swap consistency below this: WARN
CONSISTENCY_FLAG = 0.50
LENGTH_WARN = 0.08
LENGTH_FLAG = 0.15
SELF_WARN = 0.05        # on the human-adjusted delta when available
SELF_FLAG = 0.10
ALPHA = 0.05
MIN_N_DEFAULT = 10      # below this a section reports NO DATA, never FLAG


def _finding(level: str, message: str) -> Dict[str, str]:
    return {"level": level, "message": message}


def _n(count: int, noun: str) -> str:
    """Count + noun with the plural 's' only when it belongs there."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _worst_of(findings: List[Dict[str, str]]) -> str:
    return max((f["level"] for f in findings if f["level"] in ("OK", "WARN", "FLAG")),
               key=LEVELS.index, default="NO DATA")


def _section_findings(audit: Dict[str, Any], section: str) -> List[Dict[str, str]]:
    d = audit[section]
    return list(d["findings"]) if "findings" in d else [d["finding"]]


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _num(value: Optional[float], digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _pval(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if value < 0.0001:
        return f"{value:.1e}"
    return f"{value:.4f}"


def _agreement_finding(d: Dict[str, Any], min_n: int) -> Dict[str, str]:
    if d["n_labeled"] < min_n:
        return _finding("NO DATA", f"only {_n(d['n_labeled'], 'human-labeled row')} (need {min_n}); add labels to measure agreement")
    kappa = d["kappa"]
    if kappa is None:
        return _finding("NO DATA", "kappa undefined")
    if kappa < KAPPA_FLAG:
        return _finding("FLAG", f"kappa {kappa:.3f} ({d['band']}): the judge barely tracks your humans")
    if kappa < KAPPA_WARN:
        return _finding("WARN", f"kappa {kappa:.3f} ({d['band']}): usable, but spot-check disagreements")
    return _finding("OK", f"kappa {kappa:.3f} ({d['band']})")


def _position_findings(d: Dict[str, Any], min_n: int) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    if d["n_decisive"] < min_n:
        findings.append(_finding("NO DATA", f"only {_n(d['n_decisive'], 'decisive verdict')} (need {min_n})"))
    else:
        delta, p = d["delta"], d["p_value"]
        rate = d["first_win_rate"]
        side = "first" if rate is not None and rate >= 0.5 else "second"
        if delta is not None and p is not None and p < ALPHA and delta >= POSITION_FLAG:
            findings.append(_finding("FLAG", f"{side}-position answers win {_pct(rate)} (p={p:.2g}); randomize or swap-average"))
        elif delta is not None and p is not None and p < ALPHA and delta >= POSITION_WARN:
            findings.append(_finding("WARN", f"{side}-position answers win {_pct(rate)} (p={p:.2g})"))
        else:
            findings.append(_finding("OK", f"first-position win rate {_pct(rate)} is consistent with order-blindness"))
    swap = d["swap_pairs"]
    if swap["n_pairs"] >= min_n:
        cons = swap["consistency_rate"]
        if cons is not None and cons < CONSISTENCY_FLAG:
            findings.append(_finding("FLAG", f"swap consistency {_pct(cons)}: verdicts mostly follow the slot, not the model"))
        elif cons is not None and cons < CONSISTENCY_WARN:
            findings.append(_finding("WARN", f"swap consistency {_pct(cons)}: verdicts change when you swap the order"))
        else:
            findings.append(_finding("OK", f"swap consistency {_pct(cons)} over {_n(swap['n_pairs'], 'linked pair')}"))
    return findings


def _length_finding(d: Dict[str, Any], min_n: int) -> Dict[str, str]:
    if d["n_compared"] < min_n:
        return _finding("NO DATA", f"only {_n(d['n_compared'], 'decisive row')} with two unequal lengths (need {min_n})")
    delta, p, rate = d["delta"], d["p_value"], d["longer_win_rate"]
    adj = d["human_adjusted"]["adjusted_delta"]
    suffix = "" if adj is None else f"; +{adj * 100:.1f} pts over humans" if adj >= 0 else f"; {adj * 100:.1f} pts vs humans"
    if delta is not None and p is not None and p < ALPHA and delta >= LENGTH_FLAG:
        return _finding("FLAG", f"longer answer wins {_pct(rate)} (p={p:.2g}){suffix}")
    if delta is not None and p is not None and p < ALPHA and delta >= LENGTH_WARN:
        return _finding("WARN", f"longer answer wins {_pct(rate)} (p={p:.2g}){suffix}")
    return _finding("OK", f"longer answer wins {_pct(rate)}, consistent with no length preference{suffix}")


def _self_finding(d: Dict[str, Any], min_n: int) -> Dict[str, str]:
    if d["n_self"] < min_n:
        return _finding("NO DATA", f"only {_n(d['n_self'], 'decisive row')} pitting the judge's own model against another (need {min_n})")
    adj = d["human_adjusted"]["adjusted_delta"]
    if adj is not None and d["human_adjusted"]["n"] >= min_n:
        if adj >= SELF_FLAG:
            return _finding("FLAG", f"judge picks its own model {adj * 100:.1f} pts more often than humans do on the same rows")
        if adj >= SELF_WARN:
            return _finding("WARN", f"judge picks its own model {adj * 100:.1f} pts more often than humans do on the same rows")
        return _finding("OK", f"self-pick rate within {abs(adj) * 100:.1f} pts of the human rate")
    # No human baseline: fall back to the confounded raw rate, and say so.
    rate, p = d["self_win_rate"], d["p_value"]
    if rate is not None and p is not None and p < ALPHA and rate - 0.5 >= SELF_FLAG:
        return _finding("FLAG", f"own model wins {_pct(rate)} (p={p:.2g}); unlabeled, so quality is a possible confound")
    if rate is not None and p is not None and p < ALPHA and rate - 0.5 >= SELF_WARN:
        return _finding("WARN", f"own model wins {_pct(rate)} (p={p:.2g}); unlabeled, so quality is a possible confound")
    return _finding("OK", f"own model wins {_pct(rate)}; no significant self-preference detected")


def build_audit(
    records: List[Record],
    source: str,
    n_rows: int,
    n_skipped: int,
    min_n: int = MIN_N_DEFAULT,
    family: bool = True,
) -> Dict[str, Any]:
    """Run all four analyses and attach OK/WARN/FLAG findings."""
    verdict_counts = {v: sum(1 for r in records if r.verdict == v) for v in VERDICTS}
    judges = sorted({r.judge for r in records if r.judge is not None})
    models = sorted({m for r in records for m in (r.model_a, r.model_b) if m is not None})

    agreement = analyze_agreement(records).to_dict()
    position = analyze_position(records).to_dict()
    length = analyze_length(records).to_dict()
    selfpref = analyze_self_preference(records, family=family).to_dict()

    agreement["finding"] = _agreement_finding(agreement, min_n)
    position["findings"] = _position_findings(position, min_n)
    length["finding"] = _length_finding(length, min_n)
    selfpref["finding"] = _self_finding(selfpref, min_n)

    all_findings = [agreement["finding"], *position["findings"], length["finding"], selfpref["finding"]]
    worst = _worst_of(all_findings)

    return {
        "schema_version": SCHEMA_VERSION,
        "judgecal_version": __version__,
        "source": source,
        "overview": {
            "n_rows": n_rows,
            "n_parsed": len(records),
            "n_skipped": n_skipped,
            "judges": judges,
            "models": models,
            "verdicts": verdict_counts,
            "tie_rate": round_opt(proportion(verdict_counts["tie"], len(records))),
            "worst_finding": worst,
        },
        "agreement": agreement,
        "position": position,
        "length": length,
        "self_preference": selfpref,
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_json(audit: Dict[str, Any]) -> str:
    return json.dumps(audit, indent=2, sort_keys=True)


def _text_findings(findings: List[Dict[str, str]], out: List[str]) -> None:
    for f in findings:
        out.append(f"    -> {f['level']}: {f['message']}")


def render_text(audit: Dict[str, Any], sections: Optional[List[str]] = None) -> str:
    """Human-readable terminal report. ``sections`` limits to a subset."""
    all_sections = ["agreement", "position", "length", "self_preference"]
    sections = sections or all_sections
    ov = audit["overview"]
    out: List[str] = []
    out.append(f"judgecal {audit['judgecal_version']} — {audit['source']}")
    out.append(
        f"rows: {ov['n_rows']}  parsed: {ov['n_parsed']}  skipped: {ov['n_skipped']}"
        f"  judges: {', '.join(ov['judges']) or 'unknown'}"
    )
    v = ov["verdicts"]
    out.append(f"verdicts: a={v['a']}  b={v['b']}  tie={v['tie']}  (tie rate {_pct(ov['tie_rate'])})")
    out.append("")

    if "agreement" in sections:
        d = audit["agreement"]
        out.append(f"[agreement] Human agreement (n={d['n_labeled']} labeled)")
        if d["n_labeled"]:
            out.append(f"    observed agreement   {_pct(d['observed_agreement'])}")
            out.append(f"    Cohen's kappa        {_num(d['kappa'])}  ({d['band']})")
            out.append(f"    decisive-only agree  {_pct(d['decisive_agreement'])}  (n={d['n_decisive_both']})")
            out.append(f"    tie rate             judge {_pct(d['judge_tie_rate'])} vs human {_pct(d['human_tie_rate'])}")
            c = d["confusion"]
            out.append("    confusion (judge rows x human cols)   a      b      tie")
            for row in VERDICTS:
                cells = "".join(f"{c[row][col]:>7d}" for col in VERDICTS)
                out.append(f"      judge={row:<4s}                     {cells}")
        _text_findings([d["finding"]], out)
        out.append("")

    if "position" in sections:
        d = audit["position"]
        out.append(f"[position] Position bias (n={d['n_decisive']} decisive, {_n(d['n_ties'], 'tie')})")
        out.append(f"    first-position wins  {d['first_wins']}/{d['n_decisive']} = {_pct(d['first_win_rate'])}"
                   f"  [95% CI {_pct(d['ci_low'])}-{_pct(d['ci_high'])}]  p={_pval(d['p_value'])}")
        s = d["swap_pairs"]
        out.append(f"    swap pairs           {s['n_pairs']} linked  ->  consistent {s['consistent']},"
                   f" first-sticky {s['first_sticky']}, second-sticky {s['second_sticky']}, mixed {s['mixed']}")
        out.append(f"    swap consistency     {_pct(s['consistency_rate'])}")
        _text_findings(d["findings"], out)
        out.append("")

    if "length" in sections:
        d = audit["length"]
        out.append(f"[length] Length bias (n={d['n_compared']} compared)")
        out.append(f"    longer answer wins   {d['longer_wins']}/{d['n_compared']} = {_pct(d['longer_win_rate'])}"
                   f"  [95% CI {_pct(d['ci_low'])}-{_pct(d['ci_high'])}]  p={_pval(d['p_value'])}")
        out.append(f"    length correlation   {_num(d['correlation'])}  (log ratio vs verdict)")
        for b in d["buckets"]:
            out.append(f"      ratio {b['bucket']:<9s} n={b['n']:<5d} longer wins {_pct(b['longer_win_rate'])}")
        h = d["human_adjusted"]
        if h["n"]:
            out.append(f"    human baseline       judge {_pct(h['judge_longer_rate'])} vs human {_pct(h['human_longer_rate'])}"
                       f"  (adjusted delta {_num(h['adjusted_delta'])}, n={h['n']})")
        _text_findings([d["finding"]], out)
        out.append("")

    if "self_preference" in sections:
        d = audit["self_preference"]
        out.append(f"[self] Self-preference (n={d['n_self']} decisive self-vs-other, {_n(d['n_ties'], 'tie')})")
        out.append(f"    judges matched       {', '.join(d['judges_matched']) or 'none'}")
        out.append(f"    own model wins       {d['self_wins']}/{d['n_self']} = {_pct(d['self_win_rate'])}"
                   f"  [95% CI {_pct(d['ci_low'])}-{_pct(d['ci_high'])}]  p={_pval(d['p_value'])}")
        h = d["human_adjusted"]
        if h["n"]:
            out.append(f"    human baseline       judge {_pct(h['judge_self_rate'])} vs human {_pct(h['human_self_rate'])}"
                       f"  (adjusted delta {_num(h['adjusted_delta'])}, n={h['n']})")
        _text_findings([d["finding"]], out)
        out.append("")

    if set(sections) >= set(all_sections):
        out.append(f"overall: {ov['worst_finding']}")
    else:
        # A single-check command must not judge checks it did not print:
        # `judgecal position` on a length-biased log would otherwise end an
        # all-OK position report with a baffling "overall: FLAG".
        worst = _worst_of([f for s in sections for f in _section_findings(audit, s)])
        out.append(f"overall ({', '.join(sections)}): {worst}")
    return "\n".join(out)


def render_markdown(audit: Dict[str, Any]) -> str:
    """PR-comment-ready Markdown summary of the audit."""
    ov = audit["overview"]
    a, p, l, s = audit["agreement"], audit["position"], audit["length"], audit["self_preference"]
    sp = p["swap_pairs"]
    lines: List[str] = []
    lines.append(f"## judgecal audit — `{audit['source']}`")
    lines.append("")
    lines.append(f"{_n(ov['n_parsed'], 'comparison')} parsed ({ov['n_skipped']} skipped) · "
                 f"judges: {', '.join(ov['judges']) or 'unknown'} · overall: **{ov['worst_finding']}**")
    lines.append("")
    lines.append("| Check | Headline | n | Verdict |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Human agreement | kappa {_num(a['kappa'])} ({a['band'] or 'n/a'}) | {a['n_labeled']} | {a['finding']['level']} |")
    pos_level = _worst_of(p["findings"])
    lines.append(f"| Position bias | first wins {_pct(p['first_win_rate'])}, swap consistency {_pct(sp['consistency_rate'])} | {p['n_decisive']} | {pos_level} |")
    lines.append(f"| Length bias | longer wins {_pct(l['longer_win_rate'])} (adj. delta {_num(l['human_adjusted']['adjusted_delta'])}) | {l['n_compared']} | {l['finding']['level']} |")
    lines.append(f"| Self-preference | own model wins {_pct(s['self_win_rate'])} (adj. delta {_num(s['human_adjusted']['adjusted_delta'])}) | {s['n_self']} | {s['finding']['level']} |")
    lines.append("")
    lines.append("### Findings")
    lines.append("")
    for f in [a["finding"], *p["findings"], l["finding"], s["finding"]]:
        lines.append(f"- **{f['level']}** — {f['message']}")
    lines.append("")
    lines.append(f"<sub>generated offline by judgecal {audit['judgecal_version']} · schema v{audit['schema_version']}</sub>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def check_gates(
    audit: Dict[str, Any],
    min_kappa: Optional[float] = None,
    max_position_delta: Optional[float] = None,
    max_length_delta: Optional[float] = None,
    max_self_delta: Optional[float] = None,
) -> List[str]:
    """Evaluate CI gates against an audit; return violation messages.

    A gate that cannot be evaluated (metric is None) is a violation too:
    "we couldn't measure it" must not pass a check that demands the number.
    """
    violations: List[str] = []

    if min_kappa is not None:
        kappa = audit["agreement"]["kappa"]
        if kappa is None:
            violations.append(f"gate --min-kappa {min_kappa}: kappa unavailable (no human-labeled rows)")
        elif kappa < min_kappa:
            violations.append(f"gate --min-kappa {min_kappa}: kappa is {kappa:.4f}")

    if max_position_delta is not None:
        delta = audit["position"]["delta"]
        if delta is None:
            violations.append(f"gate --max-position-delta {max_position_delta}: no decisive verdicts")
        elif delta > max_position_delta:
            violations.append(f"gate --max-position-delta {max_position_delta}: delta is {delta:.4f}")

    if max_length_delta is not None:
        delta = audit["length"]["delta"]
        if delta is None:
            violations.append(f"gate --max-length-delta {max_length_delta}: no length-comparable rows")
        elif delta > max_length_delta:
            violations.append(f"gate --max-length-delta {max_length_delta}: delta is {delta:.4f}")

    if max_self_delta is not None:
        d = audit["self_preference"]
        delta = d["human_adjusted"]["adjusted_delta"]
        if delta is None:
            delta = d["delta"]  # fall back to the raw (confounded) delta
        if delta is None:
            violations.append(f"gate --max-self-delta {max_self_delta}: no self-vs-other rows")
        elif delta > max_self_delta:
            violations.append(f"gate --max-self-delta {max_self_delta}: delta is {delta:.4f}")

    return violations
