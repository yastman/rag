"""Re-export shim — canonical implementation is in ``src/`` (#1948 slice 5).

The actual implementation now lives in ``src/scoring.py``. This module
preserves the historical import surface so existing bot internals
and tests that ``patch("telegram_bot.scoring.write_scores", ...)`` keep
working unchanged.

New code under ``mini_app/`` and ``src/`` should import
directly from ``src.scoring``.
"""

from __future__ import annotations

from src.scoring import (
    score,
    write_crm_scores,
    write_history_scores,
    write_pipeline_scores,
)


__all__ = [
    "score",
    "write_crm_scores",
    "write_history_scores",
    "write_pipeline_scores",
]
