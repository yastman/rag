"""Pure error-classification helpers extracted from ``telegram_bot/bot.py`` (#1265).

Slice 1 PR-3 of the published bot.py decomposition plan.

These helpers are deliberately aiogram/langgraph/fastapi/langchain-free so they
can be imported from tests, tooling, and lightweight runtime adapters without
pulling the full bot stack. Module-level imports are restricted to stdlib
plus the local traceback-walk helper from
``telegram_bot.services.error_utils``.

Owned helpers (verbatim, byte-for-byte semantics with the pre-extract
``bot.py`` definitions; pinned by
``tests/contract/test_bot_error_classification_extraction_contract.py``):

  - ``_is_post_pipeline_cleanup_error``
  - ``_is_checkpointer_runtime_error``
"""

from __future__ import annotations

from .services.error_utils import walk_traceback_frames


def _is_post_pipeline_cleanup_error(exc: Exception) -> bool:
    """Best-effort detection for cleanup failures after graph nodes completed.

    LangGraph checkpointer/storage errors may surface during Pregel loop __aexit__
    after node execution and even after a response was already delivered.
    """
    message = str(exc).lower()
    cleanup_markers = (
        "asyncpregelloop.__aexit__",
        "pregelloop.__aexit__",
        "checkpointer",
        "pregel",
    )
    storage_markers = (
        "operationalerror",
        "redis.connectionerror",
        "consuming input failed",
        "connection lost",
        "connection closed",
        # RedisVL semantic cache errors (#524): index missing, schema mismatch,
        # RediSearch module not loaded on plain Redis instance
        "redisvlerror",
        "redissearcherror",
        "schemavalidationerror",
        "redisvl",
    )

    if any(m in message for m in cleanup_markers) and any(m in message for m in storage_markers):
        return True

    for filename, func in walk_traceback_frames(exc):
        if "langgraph" in filename and func == "__aexit__":
            return True

    return False


def _is_checkpointer_runtime_error(exc: Exception) -> bool:
    """Detect runtime checkpointer/storage failures in text agent path."""
    message = str(exc).lower()
    checkpointer_markers = (
        "checkpointer",
        "checkpoint",
        "aput",
        "pregelloop.__aexit__",
        "asyncpregelloop.__aexit__",
    )
    storage_markers = (
        "serializ",
        "json",
        "msgpack",
        "redis",
        "connection",
    )
    if any(m in message for m in checkpointer_markers) and any(
        m in message for m in storage_markers
    ):
        return True

    for filename, _ in walk_traceback_frames(exc):
        if "langgraph" in filename and "checkpoint" in filename:
            return True
    return False
