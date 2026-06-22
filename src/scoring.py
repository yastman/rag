"""Backward-compat shim — canonical implementation is in src/observability/scores.py.

Langfuse score-writing utilities shared by bot handler and RAG agent tool (#310).
Moved to src/observability/scores.py as part of the observability package consolidation.
This shim keeps the src.scoring import surface working (#2711).
"""

from __future__ import annotations

from src.observability.scores import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_history_scores,
    write_scores,
)


__all__ = [
    "compute_checkpointer_overhead_proxy_ms",
    "score",
    "write_history_scores",
    "write_scores",
]
