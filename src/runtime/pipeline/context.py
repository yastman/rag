# SPDX-License-Identifier: MIT
"""Typed pipeline state contract for rag_pipeline() (#2946).

Replaces the stringly-typed ``dict[str, Any]`` previously passed as
``state_contract``.  The shape mirrors ``PreAgentStateContract`` in
``telegram_bot.pipelines.state_contract``; the two stay in sync but live in
separate layers (src/ must not import telegram_bot/).
"""

from __future__ import annotations

from typing import Any, TypedDict


class PipelineContext(TypedDict, total=False):
    """Typed state passed from the pre-agent stage into rag_pipeline().

    All fields are optional (``total=False``) so callers can construct a
    partial context with only the keys they know about.
    """

    cache_checked: bool
    cache_hit: bool
    cache_scope: str
    embedding_bundle_ready: bool
    embedding_bundle_version: str
    dense_vector: list[float] | None
    sparse_vector: dict[str, Any] | None
    colbert_query: list[list[float]] | None
    query_type: str
    topic_hint: str | None
    filters: dict[str, Any]
    retrieval_policy: str
    grounding_mode: str


__all__ = ["PipelineContext"]
