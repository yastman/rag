"""RAG LangGraph pipeline — graph assembly.

Builds the full StateGraph with all nodes and conditional edges.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from telegram_bot.graph.edges import (
    route_after_guard,
    route_by_query_type,
    route_cache,
    route_grade,
    route_start,
)
from telegram_bot.graph.state import RAGState


logger = logging.getLogger(__name__)


def _route_by_query_type_no_guard(
    state: dict[str, Any],
) -> str:
    """Route without guard: CHITCHAT/OFF_TOPIC → respond, else → cache_check."""
    query_type = state.get("query_type", "GENERAL")
    if query_type in ("CHITCHAT", "OFF_TOPIC"):
        return "respond"
    return "cache_check"


def build_graph(
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
    message: Any | None = None,
    checkpointer: Any | None = None,
    event_stream: Any | None = None,
    show_transcription: bool = True,
    voice_language: str = "ru",
    stt_model: str = "whisper",
    content_filter_enabled: bool = True,
    guard_mode: str = "hard",
    guard_ml_enabled: bool = False,
    llm_guard_client: Any | None = None,
) -> Any:
    """Build and compile the RAG StateGraph.

    Args:
        cache: CacheLayerManager instance
        embeddings: BGEM3Embeddings instance
        sparse_embeddings: BGEM3SparseEmbeddings instance
        qdrant: QdrantService instance
        reranker: Optional ColbertRerankerService
        llm: Optional LLM instance (defaults via GraphConfig)
        message: Optional aiogram Message for streaming generate + respond_node
        checkpointer: Optional checkpointer for conversation persistence

    Returns:
        Compiled StateGraph ready for .ainvoke()
    """
    from telegram_bot.graph.nodes.cache import cache_check_node, cache_store_node
    from telegram_bot.graph.nodes.classify import classify_node
    from telegram_bot.graph.nodes.grade import grade_node
    from telegram_bot.graph.nodes.guard import guard_node
    from telegram_bot.graph.nodes.rerank import rerank_node
    from telegram_bot.graph.nodes.rewrite import rewrite_node
    from telegram_bot.graph.nodes.transcribe import make_transcribe_node

    workflow = StateGraph(RAGState)

    # Add nodes — wrap those that need injected deps via functools.partial
    workflow.add_node("classify", classify_node)  # type: ignore[type-var]

    workflow.add_node(
        "transcribe",
        make_transcribe_node(
            llm=llm,
            voice_language=voice_language,
            stt_model=stt_model,
            show_transcription=show_transcription,
            message=message,
        ),
    )

    if content_filter_enabled:
        workflow.add_node(
            "guard",
            functools.partial(
                guard_node,
                guard_mode=guard_mode,
                guard_ml_enabled=guard_ml_enabled,
                llm_guard_client=llm_guard_client,
            ),
        )

    workflow.add_node(
        "cache_check",
        functools.partial(cache_check_node, cache=cache, embeddings=embeddings),
    )

    workflow.add_node(
        "retrieve",
        functools.partial(
            retrieve_node_wrapper,
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        ),
    )

    workflow.add_node("grade", grade_node)  # type: ignore[type-var]

    workflow.add_node(
        "rerank",
        functools.partial(rerank_node, reranker=reranker),
    )

    workflow.add_node(
        "generate",
        _make_generate_node(message),
    )

    workflow.add_node(
        "rewrite",
        functools.partial(rewrite_node, llm=llm),
    )

    workflow.add_node(
        "cache_store",
        functools.partial(cache_store_node, cache=cache, event_stream=event_stream),
    )

    workflow.add_node(
        "respond",
        _make_respond_node(message),
    )

    # Conversation memory: SDK summarization (langmem) — only when checkpointer is active
    if checkpointer is not None:
        from langchain_core.messages.utils import count_tokens_approximately
        from langmem.short_term import SummarizationNode

        from telegram_bot.graph.config import GraphConfig
        from telegram_bot.observability import observe

        config = GraphConfig.from_env()
        summarize_model = _create_summarize_model(config)
        summarize = SummarizationNode(
            model=summarize_model,
            max_tokens=512,
            max_tokens_before_summary=1024,
            max_summary_tokens=256,
            token_counter=count_tokens_approximately,
            input_messages_key="messages",
            output_messages_key="messages",
        )

        @observe(name="node-summarize", capture_input=False, capture_output=False)
        async def summarize_wrapper(state: RAGState) -> RAGState:
            t0 = time.perf_counter()
            result: RAGState
            try:
                result = cast(RAGState, await summarize.ainvoke(state))
            except Exception:
                logger.warning(
                    "Summarization failed; preserving response without summary", exc_info=True
                )
                result = state.copy()
            elapsed = time.perf_counter() - t0
            result["latency_stages"] = {**state.get("latency_stages", {}), "summarize": elapsed}
            return cast(RAGState, result)

        workflow.add_node("summarize", summarize_wrapper)  # type: ignore[type-var]

    # Edges
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "transcribe": "transcribe",
            "classify": "classify",
        },
    )
    workflow.add_edge("transcribe", "classify")

    if content_filter_enabled:
        workflow.add_conditional_edges(
            "classify",
            route_by_query_type,
            {
                "respond": "respond",
                "guard": "guard",
            },
        )
        workflow.add_conditional_edges(
            "guard",
            route_after_guard,
            {
                "respond": "respond",
                "cache_check": "cache_check",
            },
        )
    else:
        workflow.add_conditional_edges(
            "classify",
            _route_by_query_type_no_guard,
            {
                "respond": "respond",
                "cache_check": "cache_check",
            },
        )

    workflow.add_conditional_edges(
        "cache_check",
        route_cache,
        {
            "respond": "respond",
            "retrieve": "retrieve",
        },
    )

    workflow.add_edge("retrieve", "grade")

    workflow.add_conditional_edges(
        "grade",
        route_grade,
        {
            "rerank": "rerank",
            "rewrite": "rewrite",
            "generate": "generate",
        },
    )

    workflow.add_edge("rerank", "generate")
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", "cache_store")
    workflow.add_edge("cache_store", "respond")

    if checkpointer is not None:
        workflow.add_edge("respond", "summarize")
        workflow.add_edge("summarize", END)
    else:
        workflow.add_edge("respond", END)

    return workflow.compile(checkpointer=checkpointer)


async def retrieve_node_wrapper(
    state: dict[str, Any],
    *,
    cache: Any,
    embeddings: Any | None = None,
    sparse_embeddings: Any,
    qdrant: Any,
) -> dict[str, Any]:
    """Wrapper for retrieve_node to match functools.partial signature."""
    from telegram_bot.graph.nodes.retrieve import retrieve_node

    return await retrieve_node(
        state,
        cache=cache,
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
    )


def _create_summarize_model(config: Any) -> Any:
    """Create a LangChain ChatOpenAI for SummarizationNode via LiteLLM proxy.

    Tracing is handled by @observe on pipeline nodes and LiteLLM proxy logging.
    CallbackHandler removed: broken context propagation in async LangGraph (#157).
    """
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    return ChatOpenAI(
        model=config.llm_model,
        api_key=SecretStr(config.llm_api_key or "no-key"),
        base_url=config.llm_base_url,
    )


def _make_generate_node(message: Any | None):
    """Create generate_node with message injected for streaming delivery."""
    from telegram_bot.graph.nodes.generate import generate_node

    if message is None:
        return generate_node

    async def generate_with_message(state: RAGState) -> dict[str, Any]:
        return await generate_node(state, message=message)

    return generate_with_message


def _make_respond_node(message: Any | None):
    """Create respond_node with message injected into state."""
    from telegram_bot.graph.nodes.respond import respond_node

    if message is None:
        return respond_node

    async def respond_with_message(state: dict[str, Any]) -> dict[str, Any]:
        state_with_msg = {**state, "message": message}
        return await respond_node(state_with_msg)

    return respond_with_message
