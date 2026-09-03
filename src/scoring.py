"""Backward-compat shim — canonical implementation is in src/observability/scores.py.

Score-writing utilities shared by bot handler and RAG agent tool (#310).
Moved to src/observability/scores.py as part of the observability package consolidation.
This shim keeps the src.scoring import surface working (#2711).
"""

from __future__ import annotations

from typing import Any

from src.observability.scores import (
    score,
    write_history_scores,
    write_scores,
)


def write_pipeline_scores(lf: Any, result: dict, *, trace_id: str = "") -> None:
    """No-op stub — tracing removed (#2844)."""


def write_crm_scores(lf: Any, messages: list, *, trace_id: str = "") -> None:
    """No-op stub — tracing removed (#2844)."""


__all__ = [
    "score",
    "write_crm_scores",
    "write_history_scores",
    "write_pipeline_scores",
    "write_scores",
]
