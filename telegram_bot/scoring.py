"""Re-export shim for Langfuse scoring helpers — canonical in ``src/`` (#1948 slice 5).

The actual implementation now lives in ``src/scoring.py``. This module
preserves the historical import surface so existing bot internals
(``telegram_bot/agents/rag_tool.py``, ``telegram_bot/handlers/command_handlers.py``,
``telegram_bot/pipelines/client.py``, ``telegram_bot/bot.py``) and tests
that ``patch("telegram_bot.scoring.write_langfuse_scores", ...)`` keep
working unchanged.

New code under ``mini_app/``, ``src/api/``, and ``src/`` should import
directly from ``src.scoring``.
"""

from __future__ import annotations

from src.scoring import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_crm_scores,
    write_history_scores,
    write_langfuse_scores,
)


__all__ = [
    "compute_checkpointer_overhead_proxy_ms",
    "score",
    "write_crm_scores",
    "write_history_scores",
    "write_langfuse_scores",
]
