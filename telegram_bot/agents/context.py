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
    kommo_client: Any | None  # KommoClient (lazy import to avoid circular)
    history_service: Any  # HistoryService
    embeddings: Any  # BGEM3HybridEmbeddings
    sparse_embeddings: Any  # BGEM3SparseEmbeddings
    qdrant: Any  # QdrantService
    cache: Any  # CacheLayerManager
    reranker: Any | None  # ColbertRerankerService or None
    llm: Any  # AsyncOpenAI
    content_filter_enabled: bool = True
    guard_mode: str = "hard"
    # Set to True by tools that deliver response directly (e.g. streaming) to prevent
    # bot.py from sending the message a second time (#428).
    response_sent: bool = False
    original_user_query: str = ""
