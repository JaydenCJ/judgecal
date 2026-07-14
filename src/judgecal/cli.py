"""judgecal command-line interface.

Subcommands: ``audit`` (everything + CI gates), one command per single check
(``agreement``, ``position``, ``length``, ``self``), and ``validate`` for
line-by-line schema feedback. Everything runs offline on a local file.

Exit codes: 0 success, 1 gate violation or invalid log (validate),
2 usage / unreadable input.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .records import LoadResult, MappingError, filter_judge, load_path, parse_mapping
from .report import (
    MIN_N_DEFAULT,
    build_audit,
    check_gates,
    render_json,
    render_markdown,
    render_text,
)

_SECTION_COMMANDS = {
    "agreement": "agreement",
    "position": "position",
    "length": "length",
    "self": "self_preference",
}


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log", help="judge log: JSON Lines or a JSON array file")
    parser.add_argument("--map", action="append", default=[], metavar="FIELD=KEY",
                        help="map a canonical field to a source key (repeatable), e.g. --map verdict=winner")
    parser.add_argument("--judge", metavar="NAME",
                        help="only audit records from this judge (exact, case-insensitive)")
    parser.add_argument("--min-n", type=int, default=MIN_N_DEFAULT, metavar="N",
                        help=f"below this sample size a check reports NO DATA (default {MIN_N_DEFAULT})")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text",
                        help="output format (default text)")
    parser.add_argument("--exact-self", action="store_true",
                        help="self-preference: require exact model-name match instead of family match")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judgecal",
        description="Audit LLM-as-judge logs offline: human agreement, position bias, "
                    "length bias, self-preference. Reads a log file; never calls a model.",
    )
    parser.add_argument("--version", action="version", version=f"judgecal {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="run all checks and print the full report")
    _add_common(audit)
    audit.add_argument("--min-kappa", type=float, metavar="K",
                       help="exit 1 unless Cohen's kappa vs humans is at least K")
    audit.add_argument("--max-position-delta", type=float, metavar="D",
                       help="exit 1 if |first-win rate - 0.5| exceeds D")
    audit.add_argument("--max-length-delta", type=float, metavar="D",
                       help="exit 1 if |longer-win rate - 0.5| exceeds D")
    audit.add_argument("--max-self-delta", type=float, metavar="D",
                       help="exit 1 if the self-preference delta (human-adjusted when possible) exceeds D")

    for name, help_text in (
        ("agreement", "human agreement only (kappa, confusion matrix)"),
        ("position", "position bias only (first-win rate, swap consistency)"),
        ("length", "length bias only (longer-win rate, ratio buckets)"),
        ("self", "self-preference only (own-model win rate vs human baseline)"),
    ):
        section = sub.add_parser(name, help=help_text)
        _add_common(section)

    validate = sub.add_parser("validate", help="check the log parses; list per-line problems")
    validate.add_argument("log", help="judge log: JSON Lines or a JSON array file")
    validate.add_argument("--map", action="append", default=[], metavar="FIELD=KEY",
                          help="map a canonical field to a source key (repeatable)")
    return parser


def _load(args: argparse.Namespace) -> LoadResult:
    mapping = parse_mapping(args.map)
    return load_path(args.log, mapping)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _run_validate(args: argparse.Namespace) -> int:
    result = _load(args)
    for issue in result.issues:
        print(str(issue))
    fatal = result.n_skipped
    warnings = sum(1 for i in result.issues if not i.fatal)
    print(f"{_plural(result.n_rows, 'row')}: {len(result.records)} valid, "
          f"{fatal} skipped, {_plural(warnings, 'warning')}")
    return 1 if fatal else 0


def _run_report(args: argparse.Namespace) -> int:
    result = _load(args)
    records = result.records
    if args.judge:
        records = filter_judge(records, args.judge)
    if not records:
        print("judgecal: no usable records after parsing/filtering", file=sys.stderr)
        for issue in result.issues[:10]:
            print(f"judgecal: {issue}", file=sys.stderr)
        return 2

    audit = build_audit(
        records,
        source=args.log,
        n_rows=result.n_rows,
        n_skipped=result.n_skipped,
        min_n=args.min_n,
        family=not args.exact_self,
    )

    if args.format == "json":
        print(render_json(audit))
    elif args.format == "markdown":
        print(render_markdown(audit))
    else:
        sections = None
        if args.command in _SECTION_COMMANDS:
            sections = [_SECTION_COMMANDS[args.command]]
        print(render_text(audit, sections))

    if args.command == "audit":
        violations = check_gates(
            audit,
            min_kappa=args.min_kappa,
            max_position_delta=args.max_position_delta,
            max_length_delta=args.max_length_delta,
            max_self_delta=args.max_self_delta,
        )
        for violation in violations:
            print(f"judgecal: FAIL: {violation}", file=sys.stderr)
        if violations:
            return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _run_validate(args)
        return _run_report(args)
    except MappingError as exc:
        print(f"judgecal: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # stdout was closed early (e.g. `judgecal audit log | head`); exit
        # quietly, and point stdout at devnull so the interpreter's flush at
        # shutdown does not raise a second BrokenPipeError.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0
    except OSError as exc:
        print(f"judgecal: cannot read {getattr(args, 'log', '?')}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
