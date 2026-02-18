"""RAG agent — wraps existing RAG graph as a supervisor tool (#240 Task 3).

Thin wrapper around build_graph().ainvoke() that exposes the existing
10-node RAG pipeline as a LangChain tool for the supervisor.

Since #310 (supervisor-only mode), this tool also writes Langfuse pipeline
scores that were previously written by the monolith handler.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.agents.tools import _get_user_context
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


def create_rag_agent(
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
) -> Any:
    """Create RAG agent tool wrapping the existing LangGraph pipeline.

    The tool delegates to `build_graph().ainvoke()` with all injected services.
    Error handling ensures the supervisor gets a controlled string response
    even if the RAG pipeline fails.
    """

    @tool
    @observe(name="tool-rag-search", capture_input=False, capture_output=False)
    async def rag_search(query: str, config: RunnableConfig) -> str:
        """Search the knowledge base for domain-specific information.

        Use this tool when the user asks about the domain topic (e.g., real estate,
        legal documents). Returns relevant information from the document collection.
        """
        from telegram_bot.graph.graph import build_graph
        from telegram_bot.graph.state import make_initial_state
        from telegram_bot.scoring import write_langfuse_scores

        lf = get_client()
        lf.update_current_span(input={"query_preview": query[:120]})

        user_id, session_id = _get_user_context(config)
        if user_id is None:
            return "Error: user context not available. Cannot perform search."

        try:
            graph = build_graph(
                cache=cache,
                embeddings=embeddings,
                sparse_embeddings=sparse_embeddings,
                qdrant=qdrant,
                reranker=reranker,
                llm=llm,
            )
            state = make_initial_state(
                user_id=user_id,
                session_id=session_id or "",
                query=query,
            )
            invoke_start = time.perf_counter()
            result = await graph.ainvoke(state)
            ainvoke_wall_ms = (time.perf_counter() - invoke_start) * 1000

            if isinstance(result, dict):
                # Compute wall-time metrics (#310)
                from telegram_bot.scoring import compute_checkpointer_overhead_proxy_ms

                result["checkpointer_overhead_proxy_ms"] = compute_checkpointer_overhead_proxy_ms(
                    result, ainvoke_wall_ms
                )
                result["pipeline_wall_ms"] = ainvoke_wall_ms
                summarize_s = result.get("latency_stages", {}).get("summarize", 0)
                result["user_perceived_wall_ms"] = ainvoke_wall_ms - (summarize_s * 1000)

                # Write full pipeline scores to Langfuse trace (#310)
                write_langfuse_scores(lf, result)

                # Online LLM-as-a-Judge sampling (#310)
                configurable = (config or {}).get("configurable", {})
                judge_rate = configurable.get("judge_sample_rate", 0)
                if (
                    judge_rate > 0
                    and not result.get("cache_hit")
                    and result.get("retrieved_context")
                    and random.random() < judge_rate
                ):
                    from telegram_bot.evaluation.runner import run_online_judge

                    trace_id = (
                        lf.get_current_trace_id() if hasattr(lf, "get_current_trace_id") else ""
                    )
                    if trace_id:
                        context_text = "\n\n".join(
                            f"[{d.get('score', 0):.2f}] {d.get('content', '')}"
                            for d in result.get("retrieved_context", [])
                        )
                        judge_model = configurable.get("judge_model", "gpt-4o-mini-cerebras-glm")
                        llm_base_url = configurable.get("llm_base_url", "http://localhost:4000")
                        _judge_task = asyncio.create_task(
                            run_online_judge(
                                langfuse=lf,
                                trace_id=trace_id,
                                query=query,
                                answer=result.get("response", ""),
                                context=context_text,
                                model=judge_model,
                                llm_base_url=llm_base_url,
                            )
                        )
                        _judge_task.add_done_callback(
                            lambda t: t.result() if not t.cancelled() else None
                        )

                response = result.get("response", "No response generated.")
                lf.update_current_span(output={"response_length": len(str(response))})
                return cast(str, response)
            return "No response generated."
        except Exception:
            logger.exception("RAG agent graph invocation failed")
            lf.update_current_span(level="ERROR", status_message="RAG graph invocation failed")
            return "Произошла ошибка при поиске. Попробуйте позже."

    return rag_search
