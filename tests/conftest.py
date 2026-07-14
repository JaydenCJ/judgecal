"""Shared factories for judgecal tests.

Every test in this suite is offline and deterministic: records are built
in-memory or written to pytest's tmp_path, and nothing depends on wall-clock
time, randomness without a seed, or the network.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from judgecal.records import Record


def rec(
    verdict: str = "a",
    human: Optional[str] = None,
    judge: Optional[str] = None,
    model_a: Optional[str] = None,
    model_b: Optional[str] = None,
    len_a: Optional[int] = None,
    len_b: Optional[int] = None,
    pair_id: Optional[str] = None,
    swapped: Optional[bool] = None,
    line: int = 0,
) -> Record:
    """Terse Record factory so tests read as data tables."""
    return Record(
        verdict=verdict, human=human, judge=judge,
        model_a=model_a, model_b=model_b, len_a=len_a, len_b=len_b,
        pair_id=pair_id, swapped=swapped, line=line,
    )


def swap_pair(pair_id: str, v1: str, v2: str, model_a: str = "m1", model_b: str = "m2") -> List[Record]:
    """A prompt judged in both orders: original (v1) then swapped (v2)."""
    return [
        rec(verdict=v1, pair_id=pair_id, model_a=model_a, model_b=model_b, swapped=False),
        rec(verdict=v2, pair_id=pair_id, model_a=model_b, model_b=model_a, swapped=True),
    ]


@pytest.fixture
def write_jsonl(tmp_path):
    """Write a list of dicts as a JSONL file and return its path as str."""

    def _write(rows: List[Dict[str, Any]], name: str = "log.jsonl") -> str:
        path = tmp_path / name
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return str(path)

    return _write
