"""Imperative history search pipeline compatibility facade."""

from __future__ import annotations

from typing import Any

from telegram_bot.agents.history_graph.nodes import (
    history_grade_node,
    history_guard_node,
    history_retrieve_node,
    history_rewrite_node,
    history_summarize_node,
    route_history_grade,
    route_history_guard,
)


class ImperativeHistoryGraph:
    """Small ``ainvoke`` facade that runs the history nodes sequentially."""

    def __init__(
        self,
        *,
        history_service: Any,
        llm: Any | None,
        guard_mode: str,
        content_filter_enabled: bool,
        relevance_threshold: float,
    ) -> None:
        self.history_service = history_service
        self.llm = llm
        self.guard_mode = guard_mode
        self.content_filter_enabled = content_filter_enabled
        self.relevance_threshold = relevance_threshold

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _ = config
        current = dict(state)
        if self.content_filter_enabled:
            current.update(await history_guard_node(current, guard_mode=self.guard_mode))
            if route_history_guard(current) == "blocked":
                return current
        current.update(await history_retrieve_node(current, history_service=self.history_service))
        current.update(await history_grade_node(current, threshold=self.relevance_threshold))
        if route_history_grade(current) == "rewrite":
            current.update(await history_rewrite_node(current, llm=self.llm))
            current.update(
                await history_retrieve_node(current, history_service=self.history_service)
            )
        current.update(await history_summarize_node(current, llm=self.llm))
        return current


def build_history_graph(
    *,
    history_service: Any,
    llm: Any | None = None,
    guard_mode: str = "hard",
    content_filter_enabled: bool = True,
    relevance_threshold: float = 0.7,
) -> Any:
    """Build the imperative history search facade."""
    return ImperativeHistoryGraph(
        history_service=history_service,
        llm=llm,
        guard_mode=guard_mode,
        content_filter_enabled=content_filter_enabled,
        relevance_threshold=relevance_threshold,
    )


__all__ = ["ImperativeHistoryGraph", "build_history_graph"]
