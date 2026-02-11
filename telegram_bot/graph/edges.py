"""Conditional edge functions for RAG LangGraph pipeline.

Three routing functions that control the graph flow:
- route_by_query_type: classify → respond or cache_check
- route_cache: cache_check → respond or retrieve
- route_grade: grade → rerank, rewrite, or generate
"""

from __future__ import annotations

from typing import Any, Literal


def route_by_query_type(
    state: dict[str, Any],
) -> Literal["respond", "cache_check"]:
    """Route after classification: CHITCHAT/OFF_TOPIC → respond, else → cache_check."""
    query_type = state.get("query_type", "GENERAL")
    if query_type in ("CHITCHAT", "OFF_TOPIC"):
        return "respond"
    return "cache_check"


def route_cache(
    state: dict[str, Any],
) -> Literal["respond", "retrieve"]:
    """Route after cache check: hit → respond, miss → retrieve."""
    if state.get("cache_hit", False):
        return "respond"
    return "retrieve"


def route_grade(
    state: dict[str, Any],
) -> Literal["rerank", "rewrite", "generate"]:
    """Route after grading: skip_rerank → generate, relevant → rerank, not relevant + retries → rewrite/generate."""
    if state.get("documents_relevant", False):
        if state.get("skip_rerank", False):
            return "generate"
        return "rerank"
    max_attempts = state.get("max_rewrite_attempts", 1)
    if (
        state.get("rewrite_count", 0) < max_attempts
        and state.get("rewrite_effective", True)
        and state.get("score_improved", True)
    ):
        return "rewrite"
    return "generate"
