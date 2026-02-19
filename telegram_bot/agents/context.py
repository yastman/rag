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
    ***REMOVED*** Set to True by tools that deliver response directly (e.g. streaming) to prevent
    ***REMOVED*** bot.py from sending the message a second time (***REMOVED***428).
    response_sent: bool = False
    original_user_query: str = ""
