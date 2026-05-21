"""BotContext — runtime context for agent tools via context_schema DI.

Replaces config["configurable"] pattern. Injected into tools via
ToolRuntime[BotContext].context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig


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


def get_bot_context(
    runtime: Any | None,
    config: RunnableConfig | dict[str, Any] | None,
) -> BotContext | None:
    """Resolve the runtime :class:`BotContext` from a tool runtime or RunnableConfig.

    SDK-native pattern (langchain v1.0+ / langgraph v1.0+ ``context_schema``):
    the agent is invoked with ``context=BotContext(...)`` and tools receive a
    typed ``runtime: Runtime[BotContext]`` parameter. ``runtime.context`` is
    then the canonical place to read the context from.

    Back-compat pattern (***REMOVED***1252 transitional): pre-migration callers wire the
    context via ``config={"configurable": {"bot_context": ctx}}``. This helper
    transparently handles both, preferring the runtime path when available so
    no site reads stale ``configurable`` data after the invoker is migrated.

    Removal plan: once :class:`telegram_bot.bot.PropertyBot` invokes the agent
    with ``context=BotContext(...)`` instead of ``configurable={"bot_context"}``,
    and tests are updated to match, drop the ``RunnableConfig`` fallback below
    and tighten the signature to a non-optional ``Runtime[BotContext]``.
    """
    ***REMOVED*** 1) Prefer runtime.context — SDK-native path.
    if runtime is not None:
        ctx = getattr(runtime, "context", None)
        if isinstance(ctx, BotContext):
            return ctx

    ***REMOVED*** 2) Fall back to RunnableConfig["configurable"]["bot_context"] for
    ***REMOVED***    invokers that haven't been migrated yet.
    if config is None:
        return None
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        if isinstance(configurable, dict):
            ctx = configurable.get("bot_context")
            if isinstance(ctx, BotContext):
                return ctx
    return None
