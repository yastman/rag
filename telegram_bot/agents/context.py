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
    kommo_client: Any | None  # KommoClient (lazy import to avoid circular)
    history_service: Any  # HistoryService
    embeddings: Any  # BGEM3HybridEmbeddings
    sparse_embeddings: Any  # BGEM3SparseEmbeddings
    qdrant: Any  # QdrantService
    cache: Any  # CacheLayerManager
    reranker: Any | None  # Optional reranker hook; deprecated ColBERT client is ignored
    llm: Any  # AsyncOpenAI
    content_filter_enabled: bool = True
    guard_mode: str = "hard"
    role: str = "client"
    manager_id: int | None = None  # Kommo responsible_user_id for manager-role flows
    # Set to True by tools that deliver response directly (e.g. streaming) to prevent
    # bot.py from sending the message a second time (#428).
    response_sent: bool = False
    # Raw user query before any agent/tool reformulation (#430).
    original_query: str = ""
    # Raw user query for pre-agent/tool guard checks (#439).
    original_user_query: str = ""
    history_relevance_threshold: float = 0.7
    history_reply_markup: Any | None = None  # side-channel for #434
    bot: Any | None = None  # aiogram Bot instance (for handoff tool, #445)
    manager_ids: list[int] | None = None  # Telegram IDs of managers (for handoff, #445)
    apartments_service: Any | None = None  # ApartmentsService (#629)
    search_event_store: Any | None = None  # SearchEventStore
    apartment_pipeline: Any | None = None  # ApartmentExtractionPipeline


def get_bot_context(
    runtime: Any | None,
    config: RunnableConfig | dict[str, Any] | None,
) -> Any | None:
    """Resolve the runtime :class:`BotContext` from a tool runtime or RunnableConfig.

    SDK-native pattern (langchain v1.0+ / langgraph v1.0+ ``context_schema``):
    the agent is invoked with ``context=BotContext(...)`` and tools receive a
    typed ``runtime: Runtime[BotContext]`` parameter. ``runtime.context`` is
    then the canonical place to read the context from.

    Back-compat pattern (#1252 transitional): pre-migration callers wire the
    context via ``config={"configurable": {"bot_context": ctx}}``. Existing
    tests and some tool harnesses use context-like mocks rather than a concrete
    ``BotContext`` instance, so the fallback intentionally preserves the old
    duck-typed behavior while preferring the runtime path when available.

    Removal plan: once :class:`telegram_bot.bot.PropertyBot` invokes the agent
    with ``context=BotContext(...)`` instead of ``configurable={"bot_context"}``,
    and tests are updated to match, drop the ``RunnableConfig`` fallback below
    and tighten the signature to a non-optional ``Runtime[BotContext]``.
    """
    # 1) Prefer runtime.context — SDK-native path.
    if runtime is not None:
        ctx = getattr(runtime, "context", None)
        if ctx is not None:
            return ctx

    # 2) Fall back to RunnableConfig["configurable"]["bot_context"] for
    #    invokers that haven't been migrated yet.
    if config is None:
        return None
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        if isinstance(configurable, dict):
            ctx = configurable.get("bot_context")
            if ctx is not None:
                return ctx
    return None
