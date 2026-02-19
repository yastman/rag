"""BotContext — runtime context for agent tools via context_schema DI.

Replaces config["configurable"] pattern. Injected into tools via
ToolRuntime[BotContext].context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BotContext:
    """Runtime context injected into agent tools.

    Fields map to services initialized in PropertyBot.__init__.
    """

    telegram_user_id: int
    session_id: str
    language: str
    kommo_client: Any | None  ***REMOVED*** KommoClient (lazy import to avoid circular)
    history_service: Any  ***REMOVED*** HistoryService
    embeddings: Any  ***REMOVED*** BGEM3HybridEmbeddings
    sparse_embeddings: Any  ***REMOVED*** BGEM3SparseEmbeddings
    qdrant: Any  ***REMOVED*** QdrantService
    cache: Any  ***REMOVED*** CacheLayerManager
    reranker: Any | None  ***REMOVED*** ColbertRerankerService or None
    llm: Any  ***REMOVED*** AsyncOpenAI
    content_filter_enabled: bool = True
    guard_mode: str = "hard"
    history_relevance_threshold: float = 0.7
    history_reply_markup: Any | None = None  ***REMOVED*** side-channel for ***REMOVED***434
