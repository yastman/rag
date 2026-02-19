"""History sub-graph assembly — retrieve → grade → rewrite → summarize (#408).

Builds and compiles a LangGraph StateGraph for agentic history search.
"""

from __future__ import annotations

import functools
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from telegram_bot.agents.history_graph.nodes import (
    history_grade_node,
    history_guard_node,
    history_retrieve_node,
    history_rewrite_node,
    history_summarize_node,
    route_history_grade,
    route_history_guard,
)
from telegram_bot.agents.history_graph.state import HistoryState


def build_history_graph(
    *,
    history_service: Any,
    llm: Any | None = None,
    guard_mode: str = "hard",
    content_filter_enabled: bool = True,
) -> Any:
    """Build and compile the history search sub-graph.

    Args:
        history_service: HistoryService instance (Qdrant + BGE-M3).
        llm: LLM instance (langfuse.openai.AsyncOpenAI). Falls back to GraphConfig.create_llm().
        guard_mode: Content filter mode — "hard" (block), "soft" (flag), "log" (log only).
        content_filter_enabled: If False, skip guard node entirely (#432).

    Returns:
        Compiled StateGraph ready for .ainvoke().
    """
    workflow = StateGraph(HistoryState)

    # Bind dependencies via functools.partial
    retrieve = functools.partial(history_retrieve_node, history_service=history_service)
    rewrite = functools.partial(history_rewrite_node, llm=llm)
    summarize = functools.partial(history_summarize_node, llm=llm)

    workflow.add_node("retrieve", cast(Any, retrieve))
    workflow.add_node("grade", cast(Any, history_grade_node))
    workflow.add_node("rewrite", cast(Any, rewrite))
    workflow.add_node("summarize", cast(Any, summarize))

    # Guard node: injection/toxicity filtering (#432)
    if content_filter_enabled:
        guard = functools.partial(history_guard_node, guard_mode=guard_mode)
        workflow.add_node("guard", cast(Any, guard))
        workflow.add_edge(START, "guard")
        workflow.add_conditional_edges(
            "guard",
            route_history_guard,
            {
                "retrieve": "retrieve",
                "__end__": END,
            },
        )
    else:
        workflow.add_edge(START, "retrieve")

    # Edges
    workflow.add_edge("retrieve", "grade")
    workflow.add_conditional_edges(
        "grade",
        route_history_grade,
        {
            "summarize": "summarize",
            "rewrite": "rewrite",
        },
    )
    workflow.add_edge("rewrite", "retrieve")  # rewrite → retrieve loop
    workflow.add_edge("summarize", END)

    return workflow.compile()
