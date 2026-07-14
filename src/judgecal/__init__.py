"""judgecal — audit LLM-as-judge logs offline.

Public API: load a log, run one analysis or the whole audit, render it.
No function in this package opens a network connection or calls a model;
judgecal only ever reads the log file you already have.
"""

__version__ = "0.1.0"

from .agreement import AgreementResult, analyze_agreement
from .length import LengthResult, analyze_length
from .position import PositionResult, analyze_position
from .records import Issue, LoadResult, Record, load_path, load_text, parse_mapping
from .report import build_audit, check_gates, render_json, render_markdown, render_text
from .selfpref import SelfPreferenceResult, analyze_self_preference

__all__ = [
    "__version__",
    "AgreementResult",
    "Issue",
    "LengthResult",
    "LoadResult",
    "PositionResult",
    "Record",
    "SelfPreferenceResult",
    "analyze_agreement",
    "analyze_length",
    "analyze_position",
    "analyze_self_preference",
    "build_audit",
    "check_gates",
    "load_path",
    "load_text",
    "parse_mapping",
    "render_json",
    "render_markdown",
    "render_text",
]
