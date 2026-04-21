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
    reranker: Any | None  ***REMOVED*** Optional reranker hook; deprecated ColBERT client is ignored
    llm: Any  ***REMOVED*** AsyncOpenAI
    content_filter_enabled: bool = True
    guard_mode: str = "hard"
    role: str = "client"
    manager_id: int | None = None  ***REMOVED*** Kommo responsible_user_id for manager-role flows
    ***REMOVED*** Set to True by tools that deliver response directly (e.g. streaming) to prevent
    ***REMOVED*** bot.py from sending the message a second time (***REMOVED***428).
    response_sent: bool = False
    ***REMOVED*** Raw user query before any agent/tool reformulation (***REMOVED***430).
    original_query: str = ""
    ***REMOVED*** Raw user query for pre-agent/tool guard checks (***REMOVED***439).
    original_user_query: str = ""
    history_relevance_threshold: float = 0.7
    history_reply_markup: Any | None = None  ***REMOVED*** side-channel for ***REMOVED***434
    bot: Any | None = None  ***REMOVED*** aiogram Bot instance (for handoff tool, ***REMOVED***445)
    manager_ids: list[int] | None = None  ***REMOVED*** Telegram IDs of managers (for handoff, ***REMOVED***445)
    apartments_service: Any | None = None  ***REMOVED*** ApartmentsService (***REMOVED***629)
    search_event_store: Any | None = None  ***REMOVED*** SearchEventStore
    apartment_pipeline: Any | None = None  ***REMOVED*** ApartmentExtractionPipeline
