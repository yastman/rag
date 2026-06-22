# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""RAG pipeline — async functions replacing 11-node LangGraph graph (#442).

Pipeline returns CONTEXT (documents, scores, latency_stages).
Agent generates ANSWER from that context.

Steps:
  1. _cache_check    — compute embedding, check semantic cache
  2. _hybrid_retrieve — hybrid RRF search via Qdrant
  3. _grade_documents — score-based relevance grading
  4. _rerank          — ColBERT reranking or score-sort fallback
  5. _rewrite_query   — LLM query reformulation (loop guard)
  6. _cache_store     — store response in semantic cache

Orchestrator: rag_pipeline() wires steps with rewrite loop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from src.retrieval.topic_classifier import detect_score_gap, get_query_topic_hint
from src.runtime.graph.config import GraphConfig
from src.runtime.pipeline._cache_stage import (
    _cache_check,
    _hybrid_retrieve,
    _lookup_search_cache,  # noqa: F401
    _store_search_results,  # noqa: F401
)
from src.runtime.pipeline._grade_rerank import (
    _grade_documents,
    _rerank,
)
from src.runtime.pipeline._retrieve import (
    _HARD_EVIDENCE_CONSTRAINTS,  # noqa: F401
    _assemble_context,
    _compute_retrieval_filters,  # noqa: F401
    _document_evidence_text,  # noqa: F401
    _embed_and_cache_query_vectors,  # noqa: F401
    _ensure_sparse_vector,  # noqa: F401
    _execute_qdrant_retrieval,  # noqa: F401
    _expand_small_to_big,
    _find_missing_evidence_constraints,
    _load_cached_query_bundle,  # noqa: F401
    _resolve_query_vectors,  # noqa: F401
    _RetrievalFilterPlan,  # noqa: F401
    _RetrievalOutcome,  # noqa: F401
    _retrieve_with_relaxation,  # noqa: F401
    _run_initial_retrieval,  # noqa: F401
    _run_relaxed_retrieval,  # noqa: F401
)
from src.runtime.pipeline._rewrite_cache import _cache_store, _rewrite_query  # noqa: F401
from src.runtime.pipeline.context import PipelineContext
from src.runtime.services.cache_policy import (
    resolve_semantic_cache_signature,
)
from src.runtime.services.query_filter_signal import detect_filter_sensitive_query
from src.runtime.services.query_preprocessor import QueryPreprocessor
from src.runtime.services.rag_core import (
    CACHEABLE_QUERY_TYPES,
    build_retrieved_context,
    check_semantic_cache,  # noqa: F401
    compute_query_embedding,  # noqa: F401
)
from src.services.bge_m3_query_bundle import BgeM3QueryVectorBundle


_T = TypeVar("_T")


def _identity_observe(*args: Any, **kwargs: Any) -> Callable[[_T], _T]:
    def decorator(func: _T) -> _T:
        return func

    return decorator


def _graph_config_from_env() -> Any:
    return GraphConfig.from_env()


def _bge_m3_query_bundle_cls() -> Any:
    return BgeM3QueryVectorBundle


def _new_query_preprocessor() -> QueryPreprocessor:
    return QueryPreprocessor()


def _build_retrieved_context(*args: Any, **kwargs: Any) -> Any:
    return build_retrieved_context(*args, **kwargs)


def _cacheable_query_types() -> set[str]:
    return set(CACHEABLE_QUERY_TYPES)


logger = logging.getLogger(__name__)


_CONFIDENT_TRIM_TOP_K = 3


# ---------------------------------------------------------------------------
# Stage helpers extracted from rag_pipeline to reduce CC (#3030)
# ---------------------------------------------------------------------------


async def _run_rerank_and_trim(
    query: str,
    documents: list[Any],
    *,
    cache: Any,
    reranker: Any | None,
    config: Any,
    retrieve_result: dict[str, Any],
    grade_result: dict[str, Any],
    latency_stages: dict[str, float],
) -> tuple[list[Any], bool, bool, bool, dict[str, float]]:
    """Run rerank (or skip), detect score gap, trim confident leaders.

    Returns: (final_docs, rerank_applied, rerank_cache_hit, gap_confident, latency_stages)
    """
    rerank_from_retrieve = retrieve_result.get("rerank_applied", False)
    if grade_result["skip_rerank"] or rerank_from_retrieve:
        final_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[
            : config.rerank_top_k
        ]
        rerank_applied = rerank_from_retrieve
        rerank_cache_hit = False
    else:
        rerank_result = await _rerank(
            query,
            documents,
            cache=cache,
            reranker=reranker,
            top_k=config.rerank_top_k,
            latency_stages=latency_stages,
        )
        latency_stages = rerank_result["latency_stages"]
        final_docs = rerank_result["documents"]
        rerank_applied = rerank_result["rerank_applied"]
        rerank_cache_hit = rerank_result["rerank_cache_hit"]

    final_gap = detect_score_gap(
        [doc.get("score", 0.0) for doc in final_docs if isinstance(doc, dict)]
    )
    gap_confident = bool(final_gap["confident"])
    if gap_confident and len(final_docs) > _CONFIDENT_TRIM_TOP_K:
        logger.info(
            "Score gap confident, trimming final docs",
            extra={
                "gap_ratio": final_gap.get("ratio", 0.0),
                "before_count": len(final_docs),
                "after_count": _CONFIDENT_TRIM_TOP_K,
            },
        )
        final_docs = final_docs[:_CONFIDENT_TRIM_TOP_K]

    return final_docs, rerank_applied, rerank_cache_hit, gap_confident, latency_stages


async def _try_build_result(
    query: str,
    current_query: str,
    final_docs: list[Any],
    *,
    qdrant: Any,
    config: Any,
    retrieve_result: dict[str, Any],
    latency_stages: dict[str, float],
    embeddings_cache_hit: bool,
    rerank_applied: bool,
    rerank_cache_hit: bool,
    grade_confidence: float,
    rewrite_count: int,
    query_type: str,
    query_embedding: list[float] | None,
    cache_embedding: list[float] | None,
    topic_hint: Any,
    gap_confident: bool,
    skip_rewrite: bool,
    semantic_cache_already_checked: bool,
) -> dict[str, Any]:
    """Check missing evidence, expand small-to-big, assemble and return result."""
    missing_evidence = _find_missing_evidence_constraints(query, final_docs)
    if missing_evidence:
        result = _assemble_context(
            query=current_query,
            original_query=query,
            documents=[],
            latency_stages=latency_stages,
            cache_hit=False,
            embeddings_cache_hit=embeddings_cache_hit,
            search_cache_hit=retrieve_result.get("search_cache_hit", False),
            search_results_count=retrieve_result["search_results_count"],
            rerank_applied=rerank_applied,
            rerank_cache_hit=rerank_cache_hit,
            grade_confidence=grade_confidence,
            rewrite_count=rewrite_count,
            query_type=query_type,
            query_embedding=query_embedding,
            cache_key_embedding=cache_embedding,
            retrieved_context=[],
            retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
            retrieval_error_type=retrieve_result.get("retrieval_error_type"),
            topic_hint=topic_hint,
            score_gap_confident=gap_confident,
            missing_evidence_constraints=missing_evidence,
        )
    else:
        await _expand_small_to_big(final_docs, qdrant=qdrant, config=config)
        result = _assemble_context(
            query=current_query,
            original_query=query,
            documents=final_docs,
            latency_stages=latency_stages,
            cache_hit=False,
            embeddings_cache_hit=embeddings_cache_hit,
            search_cache_hit=retrieve_result.get("search_cache_hit", False),
            search_results_count=retrieve_result["search_results_count"],
            rerank_applied=rerank_applied,
            rerank_cache_hit=rerank_cache_hit,
            grade_confidence=grade_confidence,
            rewrite_count=rewrite_count,
            query_type=query_type,
            query_embedding=query_embedding,
            cache_key_embedding=cache_embedding,
            retrieved_context=retrieve_result.get("retrieved_context", []),
            retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
            retrieval_error_type=retrieve_result.get("retrieval_error_type"),
            topic_hint=topic_hint,
            score_gap_confident=gap_confident,
        )
    result["skip_rewrite"] = skip_rewrite
    result["semantic_cache_already_checked"] = semantic_cache_already_checked
    return result


def _init_pipeline_state(
    query: str,
    cache_key: str,
    *,
    state_contract: PipelineContext | None,
    semantic_cache_already_checked: bool,
) -> tuple[Any, Any, bool, Any, bool]:
    """Extract state_contract fields, compute filter signature and topic hint.

    Returns: (contract_filters, topic_hint, semantic_cache_prechecked,
              filter_signature, filter_sensitive)
    """
    contract_topic_hint = state_contract.get("topic_hint") if state_contract is not None else None
    contract_filters = state_contract.get("filters") if state_contract is not None else None
    topic_hint = contract_topic_hint or get_query_topic_hint(query)
    filter_signature = resolve_semantic_cache_signature(
        filters=contract_filters if isinstance(contract_filters, dict) else None
    )
    filter_sensitive = (
        detect_filter_sensitive_query(cache_key).is_filter_sensitive
        if filter_signature is None
        else True
    )
    prechecked = semantic_cache_already_checked or (filter_sensitive and filter_signature is None)
    return contract_filters, topic_hint, prechecked, filter_signature, filter_sensitive


def _unpack_cache_result(
    cache_result: dict[str, Any],
    *,
    latency_stages: dict[str, float],
) -> tuple[list[float] | None, Any, dict[str, float], list[list[float]] | None, bool]:
    """Unpack typed fields from cache_result dict.

    Returns: (cache_embedding, cache_sparse, latency_stages, colbert_query, embeddings_cache_hit)
    """
    cache_embedding_value = cache_result.get("query_embedding")
    cache_embedding: list[float] | None = (
        cache_embedding_value if isinstance(cache_embedding_value, list) else None
    )
    cache_sparse: Any = cache_result.get("sparse_embedding")
    latency_stages_value = cache_result.get("latency_stages")
    latency_stages = latency_stages_value if isinstance(latency_stages_value, dict) else {}
    colbert_query_value = cache_result.get("colbert_query")
    colbert_query: list[list[float]] | None = (
        colbert_query_value if isinstance(colbert_query_value, list) else None
    )
    embeddings_cache_hit = bool(cache_result.get("embeddings_cache_hit", False))
    return cache_embedding, cache_sparse, latency_stages, colbert_query, embeddings_cache_hit


async def _resolve_cache_stage(
    cache_key: str,
    query_type: str,
    user_id: int,
    *,
    cache: Any,
    embeddings: Any,
    agent_role: str | None,
    pre_computed_embedding: list[float] | None,
    pre_computed_sparse: Any,
    pre_computed_colbert: list[list[float]] | None,
    semantic_cache_prechecked: bool,
    semantic_cache_filter_sensitive: bool,
    semantic_cache_filter_signature: Any,
    latency_stages: dict[str, float],
    state_contract: PipelineContext | None,
) -> tuple[dict[str, Any], bool]:
    """Run cache stage: fast-path from state_contract or full _cache_check.

    Returns (cache_result, semantic_cache_prechecked).
    """
    if (
        state_contract is not None
        and state_contract.get("cache_checked") is True
        and state_contract.get("cache_hit") is False
        and state_contract.get("embedding_bundle_ready") is True
    ):
        return {
            "cache_hit": False,
            "cached_response": None,
            "query_embedding": state_contract.get("dense_vector"),
            "sparse_embedding": state_contract.get("sparse_vector"),
            "embeddings_cache_hit": False,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": state_contract.get("colbert_query"),
            "latency_stages": latency_stages,
        }, True

    result = await _cache_check(
        cache_key,
        query_type,
        user_id,
        cache=cache,
        embeddings=embeddings,
        latency_stages=latency_stages,
        agent_role=agent_role,
        pre_computed_embedding=pre_computed_embedding,
        pre_computed_sparse=pre_computed_sparse,
        pre_computed_colbert=pre_computed_colbert,
        semantic_cache_already_checked=semantic_cache_prechecked,
        semantic_cache_filter_sensitive=semantic_cache_filter_sensitive,
        semantic_cache_filter_signature=semantic_cache_filter_signature,
    )
    return result, semantic_cache_prechecked


# ---------------------------------------------------------------------------
# Step 1+2+3+4: Cache check, retrieve, grade, rerank — see submodules
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 5+6: Rewrite query and cache store — see _rewrite_cache.py
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Orchestrator: rag_pipeline()
# ---------------------------------------------------------------------------


async def rag_pipeline(
    query: str,
    *,
    user_id: int,
    session_id: str,
    query_type: str = "GENERAL",
    original_query: str = "",
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
    agent_role: str | None = None,
    state_contract: PipelineContext | None = None,
    pre_computed_embedding: list[float] | None = None,
    pre_computed_sparse: Any = None,
    pre_computed_colbert: list[list[float]] | None = None,
    semantic_cache_already_checked: bool = False,
    skip_rewrite: bool = False,
) -> dict[str, Any]:
    """Execute RAG pipeline: cache → retrieve → grade → rerank → rewrite loop → cache_store.

    Returns context dict with documents, scores, latency_stages, and pipeline metadata.
    The caller (agent) is responsible for generating the final answer from documents.

    Args:
        query: The (possibly reformulated) query used for retrieval.
        original_query: The original user query before agent reformulation.
            Used as the semantic cache key so repeated user queries hit the cache
            even when the agent reformulates them differently. Falls back to query
            when empty (voice path, direct calls).
    """
    config = _graph_config_from_env()

    # cache_key: use original user query for semantic cache so repeated queries hit
    # even when the agent reformulates them. Falls back to query when not provided.
    cache_key = original_query or query

    latency_stages: dict[str, float] = {}
    rewrite_count = 0
    rewrite_effective = True
    grade_confidence = 0.0
    current_query = query
    query_embedding: list[float] | None = None
    (
        contract_filters,
        topic_hint,
        semantic_cache_prechecked,
        semantic_cache_filter_signature,
        semantic_cache_filter_sensitive,
    ) = _init_pipeline_state(
        query,
        cache_key,
        state_contract=state_contract,
        semantic_cache_already_checked=semantic_cache_already_checked,
    )

    # Step 1: Cache check (use cache_key = original user query)
    # Pass pre_computed_embedding when caller already computed it (avoids redundant BGE-M3 call).
    cache_result, semantic_cache_prechecked = await _resolve_cache_stage(
        cache_key,
        query_type,
        user_id,
        cache=cache,
        embeddings=embeddings,
        agent_role=agent_role,
        pre_computed_embedding=pre_computed_embedding,
        pre_computed_sparse=pre_computed_sparse,
        pre_computed_colbert=pre_computed_colbert,
        semantic_cache_prechecked=semantic_cache_prechecked,
        semantic_cache_filter_sensitive=semantic_cache_filter_sensitive,
        semantic_cache_filter_signature=semantic_cache_filter_signature,
        latency_stages=latency_stages,
        state_contract=state_contract,
    )
    semantic_cache_already_checked = semantic_cache_prechecked
    # Unpack typed fields from cache_result
    cache_embedding, cache_sparse, latency_stages, colbert_query, embeddings_cache_hit = (
        _unpack_cache_result(cache_result, latency_stages=latency_stages)
    )

    if cache_result.get("embedding_error"):
        return {
            "response": cache_result.get("error_response", ""),
            "cache_hit": False,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": False,
            "embedding_error": True,
            "embedding_error_type": cache_result.get("embedding_error_type"),
            "latency_stages": latency_stages,
            "rewrite_count": 0,
            "query_type": query_type,
            "retrieved_context": [],
            "semantic_cache_already_checked": semantic_cache_already_checked,
        }

    if cache_result["cache_hit"]:
        return {
            "response": cache_result["cached_response"],
            "cache_hit": True,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": embeddings_cache_hit,
            "embedding_error": False,
            "embedding_error_type": None,
            "latency_stages": latency_stages,
            "rewrite_count": 0,
            "query_type": query_type,
            "retrieved_context": [],
            "semantic_cache_already_checked": semantic_cache_already_checked,
        }

    # For retrieval, use reformulated query embedding.
    # If cache_key differs from query (agent reformulated), pre-fetch the
    # reformulated query embedding for the FIRST retrieval attempt. This avoids a
    # redundant BGE-M3 call in _hybrid_retrieve on warm requests (#513).
    # Subsequent iterations after _rewrite_query set query_embedding = None and
    # let _hybrid_retrieve handle cache lookup for those new rewritten queries.
    if cache_key != query:
        # Agent reformulated query — all pre-computed embeddings are for original text.
        # Let _hybrid_retrieve do ONE combined aembed_hybrid_with_colbert call (#951).
        query_embedding = None
        colbert_query = None
        query_sparse: Any = None
    else:
        query_embedding = cache_embedding
        query_sparse = cache_sparse  # reuse sparse from _cache_check for this query (#571)

    # Retrieve → grade → (rerank | rewrite loop)
    for _attempt in range(config.max_rewrite_attempts + 1):
        # Step 2: Hybrid retrieve
        retrieve_result = await _hybrid_retrieve(
            current_query,
            query_embedding,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
            embeddings=embeddings,
            colbert_query=colbert_query,
            sparse_embedding=query_sparse,
            filters=contract_filters if isinstance(contract_filters, dict) else None,
            topic_hint=topic_hint,
            latency_stages=latency_stages,
        )
        latency_stages = retrieve_result["latency_stages"]
        documents = retrieve_result["documents"]
        query_embedding = retrieve_result.get("query_embedding", query_embedding)
        colbert_query = retrieve_result.get("colbert_query", colbert_query)

        # Step 3: Grade documents
        grade_result = await _grade_documents(
            documents,
            grade_confidence,
            latency_stages=latency_stages,
        )
        latency_stages = grade_result["latency_stages"]
        grade_confidence = grade_result["grade_confidence"]

        if grade_result["documents_relevant"]:
            # Step 4: Rerank, gap detection, trim
            (
                final_docs,
                rerank_applied,
                rerank_cache_hit,
                final_gap_confident,
                latency_stages,
            ) = await _run_rerank_and_trim(
                current_query,
                documents,
                cache=cache,
                reranker=reranker,
                config=config,
                retrieve_result=retrieve_result,
                grade_result=grade_result,
                latency_stages=latency_stages,
            )
            return await _try_build_result(
                query,
                current_query,
                final_docs,
                qdrant=qdrant,
                config=config,
                retrieve_result=retrieve_result,
                latency_stages=latency_stages,
                embeddings_cache_hit=embeddings_cache_hit,
                rerank_applied=rerank_applied,
                rerank_cache_hit=rerank_cache_hit,
                grade_confidence=grade_confidence,
                rewrite_count=rewrite_count,
                query_type=query_type,
                query_embedding=query_embedding,
                cache_embedding=cache_embedding,
                topic_hint=topic_hint,
                gap_confident=final_gap_confident,
                skip_rewrite=skip_rewrite,
                semantic_cache_already_checked=semantic_cache_already_checked,
            )

        # Check if we should rewrite
        if not (
            rewrite_count < config.max_rewrite_attempts
            and not skip_rewrite
            and rewrite_effective
            and grade_result.get("score_improved", True)
        ):
            break

        # Step 5: Rewrite query
        rewrite_result = await _rewrite_query(
            current_query,
            rewrite_count,
            llm=llm,
            latency_stages=latency_stages,
        )
        latency_stages = rewrite_result["latency_stages"]
        current_query = rewrite_result["rewritten_query"]
        rewrite_count = rewrite_result["rewrite_count"]
        rewrite_effective = rewrite_result["rewrite_effective"]
        topic_hint = get_query_topic_hint(current_query)
        query_embedding = None  # Force re-embed on next retrieve
        colbert_query = None  # Force re-encode ColBERT on next retrieve
        query_sparse = None  # Force re-compute sparse on next retrieve (query changed)

    # Fallback: ran out of rewrites with only irrelevant documents.
    # Do not leak "best available" unrelated context into answer generation.
    result = _assemble_context(
        query=current_query,
        original_query=query,
        documents=[],
        latency_stages=latency_stages,
        cache_hit=False,
        embeddings_cache_hit=embeddings_cache_hit,
        search_cache_hit=retrieve_result.get("search_cache_hit", False),
        search_results_count=retrieve_result["search_results_count"],
        rerank_applied=False,
        rerank_cache_hit=False,
        grade_confidence=grade_confidence,
        rewrite_count=rewrite_count,
        query_type=query_type,
        query_embedding=query_embedding,
        cache_key_embedding=cache_embedding,
        retrieved_context=[],
        retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
        retrieval_error_type=retrieve_result.get("retrieval_error_type"),
        topic_hint=topic_hint,
        score_gap_confident=False,
        missing_evidence_constraints=_find_missing_evidence_constraints(query, documents),
    )
    result["skip_rewrite"] = skip_rewrite
    result["semantic_cache_already_checked"] = semantic_cache_already_checked
    return result


# _expand_small_to_big and _assemble_context — see _retrieve.py
