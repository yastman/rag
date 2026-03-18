from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict, cast


EMBEDDING_BUNDLE_VERSION = "bge_m3_hybrid_colbert"
RETRIEVAL_POLICY_TOPIC_THEN_RELAX = "topic_then_relax"


class PreAgentStateContract(TypedDict, total=False):
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
    retrieval_policy: str
    grounding_mode: str


def build_pre_agent_miss_contract(
    *,
    query_type: str,
    topic_hint: str | None,
    dense_vector: list[float] | None,
    sparse_vector: dict[str, Any] | None,
    colbert_query: list[list[float]] | None,
    grounding_mode: str,
) -> PreAgentStateContract:
    return {
        "cache_checked": True,
        "cache_hit": False,
        "cache_scope": "rag",
        "embedding_bundle_ready": dense_vector is not None,
        "embedding_bundle_version": EMBEDDING_BUNDLE_VERSION,
        "dense_vector": dense_vector,
        "sparse_vector": sparse_vector,
        "colbert_query": colbert_query,
        "query_type": query_type,
        "topic_hint": topic_hint,
        "retrieval_policy": RETRIEVAL_POLICY_TOPIC_THEN_RELAX,
        "grounding_mode": grounding_mode,
    }


def coerce_pre_agent_state_contract(
    store: Mapping[str, Any] | None,
    *,
    query_type: str,
    topic_hint: str | None = None,
    grounding_mode: str = "",
) -> PreAgentStateContract | None:
    if not store:
        return None

    existing = store.get("state_contract")
    if isinstance(existing, dict):
        return cast(PreAgentStateContract, existing)

    dense_vector = store.get("cache_key_embedding")
    sparse_vector = store.get("cache_key_sparse")
    colbert_query = store.get("cache_key_colbert")
    if dense_vector is None and sparse_vector is None and colbert_query is None:
        return None

    dense = dense_vector if isinstance(dense_vector, list) else None
    sparse = sparse_vector if isinstance(sparse_vector, dict) else None
    colbert = colbert_query if isinstance(colbert_query, list) else None
    return build_pre_agent_miss_contract(
        query_type=query_type,
        topic_hint=topic_hint,
        dense_vector=dense,
        sparse_vector=sparse,
        colbert_query=colbert,
        grounding_mode=grounding_mode,
    )
