"""LangChain Embeddings wrappers for BGE-M3 API — back-compat re-export.

The canonical implementation moved to
:mod:`src.runtime.integrations.embeddings` as the second slice of the
reverse-layering fix (#2045 / #2049). This module remains so that
existing ``from telegram_bot.integrations.embeddings import …`` imports
across ``telegram_bot/``, ``tests/``, and the rest of the repo continue
to work unchanged.
"""

from src.runtime.integrations.embeddings import (
    BGEM3Embeddings,
    BGEM3HybridEmbeddings,
    BGEM3SparseEmbeddings,
)


__all__ = [
    "BGEM3Embeddings",
    "BGEM3HybridEmbeddings",
    "BGEM3SparseEmbeddings",
]
