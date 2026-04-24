"""RAG search tool — wraps async rag_pipeline (#442).

Pipeline returns CONTEXT (documents, scores, latency_stages).
Agent generates ANSWER from the returned context string.

Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.runtime import Runtime

from telegram_bot.agents.rag_pipeline import rag_pipeline
from telegram_bot.graph.nodes.classify import classify_query
from telegram_bot.graph.nodes.guard import guard_node
from telegram_bot.observability import get_client, observe
from telegram_bot.pipelines.state_contract import PreAgentStateContract
from telegram_bot.scoring import write_langfuse_scores


logger = logging.getLogger(__name__)


def _format_context(result: dict) -> str:
    """Format pipeline result as context string for agent LLM."""
    if result.get("response"):
        return str(result["response"])

    documents = result.get("documents", [])
    if not documents:
        return "Ничего не найдено по вашему запросу."

    parts: list[str] = []
    for i, doc in enumerate(documents, 1):
        if not isinstance(doc, dict):
            continue
        text = doc.get("text", "")
        score = doc.get("score", 0)
        meta = doc.get("metadata", {})
        source = meta.get("source", meta.get("title", ""))
        header = f"[{i}] (score: {score:.4f})"
        if source:
            header += f" — {source}"
        parts.append(f"{header}\n{text}")

    return "\n\n".join(parts) if parts else "Ничего не найдено по вашему запросу."


@tool
@observe(name="tool-rag-search", capture_input=False, capture_output=False)
async def rag_search(
    query: str,
    config: RunnableConfig,
    property_type: str | None = None,
    budget_range: str | None = None,
) -> str:
    """Search real estate knowledge base — MUST be called for any property question.

    Use this tool for ALL questions about: properties, prices, districts, cities,
    residence permits (ВНЖ), documents, FAQ, buying/renting process, mortgage,
    company services, legal matters. NEVER answer these from your own knowledge.

    Args:
        query: The search query.
        property_type: Optional filter by property type.
        budget_range: Optional filter by budget range.
    """
    configurable = config.get("configurable", {})
    ctx = configurable.get("bot_context")

    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "property_type": property_type,
            "budget_range": budget_range,
        }
    )

    try:
        query_type = classify_query(query)
        guard_result: dict = {}
        guard_mode = ctx.guard_mode if ctx else "hard"
        content_filter_enabled = ctx.content_filter_enabled if ctx else True

        if content_filter_enabled:
            # Guard the original user text when available (#439), not the agent-reformulated query.
            # Agent reformulation can sanitize malicious queries, bypassing guard detection.
            original_text = ctx.original_user_query if ctx and ctx.original_user_query else query
            guard_result = await guard_node(
                {"messages": [{"content": original_text}], "latency_stages": {}},
                Runtime(context={"guard_mode": guard_mode}),
            )
            if guard_result.get("guard_blocked"):
                pipeline_wall_ms = 0.0
                result = {
                    "response": guard_result.get(
                        "response",
                        "Извините, ваш запрос не может быть обработан.",
                    ),
                    "cache_hit": False,
                    "documents": [],
                    "search_results_count": 0,
                    "rerank_applied": False,
                    "grade_confidence": 0.0,
                    "embeddings_cache_hit": False,
                    "embedding_error": False,
                    "embedding_error_type": None,
                    "latency_stages": guard_result.get("latency_stages", {}),
                    "rewrite_count": 0,
                    "query_type": query_type,
                    "query_embedding": None,
                    "retrieved_context": [],
                    "injection_detected": guard_result.get("injection_detected", False),
                    "injection_risk_score": guard_result.get("injection_risk_score", 0.0),
                    "injection_pattern": guard_result.get("injection_pattern"),
                }
                result["pipeline_wall_ms"] = pipeline_wall_ms
                result["e2e_latency_ms"] = pipeline_wall_ms
                result["user_perceived_wall_ms"] = pipeline_wall_ms

                trace_id = lf.get_current_trace_id() or ""
                try:
                    write_langfuse_scores(lf, result, trace_id=trace_id)
                except Exception:
                    logger.warning("Failed to write Langfuse scores in rag_search", exc_info=True)

                result_store = configurable.get("rag_result_store")
                if isinstance(result_store, dict):
                    result_store.update(result)

                context = _format_context(result)
                lf.update_current_span(output={"response_length": len(context)})
                return context

        # Reuse pre-computed embedding stashed by pre-agent cache check (#563)
        result_store = configurable.get("rag_result_store")
        pre_computed_embedding: list[float] | None = None
        pre_computed_sparse: Any = None
        pre_computed_colbert: list[list[float]] | None = None
        state_contract: PreAgentStateContract | None = None
        semantic_cache_already_checked = False
        if isinstance(result_store, dict):
            pre_computed_embedding = result_store.get("cache_key_embedding")
            pre_computed_sparse = result_store.get("cache_key_sparse")
            pre_computed_colbert = result_store.get("cache_key_colbert")
            cached_state_contract = result_store.get("state_contract")
            if isinstance(cached_state_contract, dict):
                state_contract = cast(PreAgentStateContract, cached_state_contract)
            semantic_cache_already_checked = bool(
                result_store.get("semantic_cache_already_checked")
            )

        invoke_start = time.perf_counter()
        result = await rag_pipeline(
            query,
            user_id=ctx.telegram_user_id if ctx else 0,
            session_id=ctx.session_id if ctx else "",
            query_type=query_type,
            original_query=ctx.original_query if ctx else "",
            cache=ctx.cache if ctx else None,
            embeddings=ctx.embeddings if ctx else None,
            sparse_embeddings=ctx.sparse_embeddings if ctx else None,
            qdrant=ctx.qdrant if ctx else None,
            reranker=ctx.reranker if ctx else None,
            llm=ctx.llm if ctx else None,
            agent_role=ctx.role if ctx else None,
            state_contract=state_contract,
            pre_computed_embedding=pre_computed_embedding,
            pre_computed_sparse=pre_computed_sparse,
            pre_computed_colbert=pre_computed_colbert,
            semantic_cache_already_checked=semantic_cache_already_checked,
        )
        pipeline_wall_ms = (time.perf_counter() - invoke_start) * 1000

        # Streaming hook (#428): when streaming is restored for the agent text path
        # (i.e. the pipeline delivers the final answer directly to Telegram via
        # generate_node with a live message object), set ctx.response_sent = True here
        # so that _handle_query_supervisor in bot.py does not send the message again.
        # Example: if result.get("response_sent") and ctx is not None:
        #              ctx.response_sent = True

        if guard_result:
            if guard_result.get("injection_detected"):
                result["injection_detected"] = True
                result["injection_risk_score"] = guard_result.get("injection_risk_score", 0.0)
                result["injection_pattern"] = guard_result.get("injection_pattern")
            guard_latency = guard_result.get("latency_stages", {}).get("guard")
            if guard_latency is not None:
                result["latency_stages"] = {
                    **result.get("latency_stages", {}),
                    "guard": guard_latency,
                }

        result["pipeline_wall_ms"] = pipeline_wall_ms
        result["e2e_latency_ms"] = pipeline_wall_ms
        summarize_s = result.get("latency_stages", {}).get("summarize", 0)
        result["user_perceived_wall_ms"] = pipeline_wall_ms - (summarize_s * 1000)

        trace_id = lf.get_current_trace_id() or ""

        # Observability must stay fail-soft: scoring errors must not break user response.
        try:
            write_langfuse_scores(lf, result, trace_id=trace_id)
        except Exception:
            logger.warning("Failed to write Langfuse scores in rag_search", exc_info=True)

        # Store full result for caller via side-channel (#426)
        result_store = configurable.get("rag_result_store")
        if isinstance(result_store, dict):
            result_store.update(result)

        context = _format_context(result)
        lf.update_current_span(output={"response_length": len(context)})
        return context

    except Exception:
        logger.exception("RAG pipeline failed")
        lf.update_current_span(level="ERROR", status_message="RAG pipeline failed")
        return "Произошла ошибка при поиске. Попробуйте позже."
