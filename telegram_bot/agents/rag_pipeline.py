"""RAG pipeline — async functions replacing 11-node LangGraph graph (#442).

Pipeline returns CONTEXT (documents, scores, latency_stages).
Agent generates ANSWER from that context.

Steps:
  1. _cache_check    — compute embedding, check semantic cache  (cache_stage.py)
  2. _hybrid_retrieve — hybrid RRF search via Qdrant            (retrieval_stage.py)
  3. _grade_documents — score-based relevance grading
  4. _rerank          — ColBERT reranking or score-sort fallback
  5. _rewrite_query   — LLM query reformulation (loop guard)
  6. _cache_store     — store response in semantic cache        (cache_stage.py)

Orchestrator: rag_pipeline() wires steps with rewrite loop.
"""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from src.retrieval.topic_classifier import detect_score_gap, get_query_topic_hint
from telegram_bot.agents.cache_stage import _cache_check
from telegram_bot.agents.retrieval_stage import _hybrid_retrieve
from telegram_bot.pipelines.state_contract import PreAgentStateContract
from telegram_bot.services.cache_policy import resolve_semantic_cache_signature
from telegram_bot.services.metrics import record_pipeline_event
from telegram_bot.services.query_filter_signal import detect_filter_sensitive_query
from telegram_bot.services.query_preprocessor import expand_short_query
from telegram_bot.services.rag_core import (
    perform_rerank,
    rewrite_query_via_llm,
)


logger = logging.getLogger(__name__)

# top_k=7 for reranking. Standard in literature; balances latency vs recall for reranking candidate pool.
# 3 was too restrictive — comprehensive queries (e.g. list all ВНЖ types) were losing chunks.
_DEFAULT_RERANK_TOP_K = 7
_CONFIDENT_TRIM_TOP_K = 3


# ---------------------------------------------------------------------------
# Step 1: Cache check (see cache_stage.py)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Step 2: Hybrid retrieve (see retrieval_stage.py)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Step 3: Grade documents
# ---------------------------------------------------------------------------


async def _grade_documents(
    documents: list[dict[str, Any]],
    prev_confidence: float,
    *,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Grade retrieved documents by relevance using score-based heuristic.

    Returns dict with documents_relevant, grade_confidence, skip_rerank, score_improved.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**latency_stages, "grade": elapsed},
        }

    scores = [doc.get("score", 0) for doc in documents if isinstance(doc, dict)]
    if not scores:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no valid scored documents (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**latency_stages, "grade": elapsed},
        }

    top_score = max(scores)
    score_gap = detect_score_gap(sorted(scores, reverse=True))

    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()
    relevant = top_score > config.relevance_threshold_rrf
    skip_rerank = relevant and top_score >= config.skip_rerank_threshold

    delta = top_score - prev_confidence
    score_improved = delta >= config.score_improvement_delta or prev_confidence == 0.0

    elapsed = time.perf_counter() - t0
    logger.info(
        "grade: top_score=%.4f prev=%.4f delta=%.4f improved=%s "
        "threshold=%.3f relevant=%s skip_rerank=%s (%d docs, %.3fs)",
        top_score,
        prev_confidence,
        delta,
        score_improved,
        config.relevance_threshold_rrf,
        relevant,
        skip_rerank,
        len(documents),
        elapsed,
    )
    record_pipeline_event("score_gap_confident", 1 if score_gap["confident"] else 0)

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "score_improved": score_improved,
        "score_gap_confident": score_gap["confident"],
        "latency_stages": {**latency_stages, "grade": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 4: Rerank
# ---------------------------------------------------------------------------


async def _rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    cache: Any | None = None,
    reranker: Any | None = None,
    top_k: int = _DEFAULT_RERANK_TOP_K,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rerank documents using ColBERT or score-based fallback.

    Returns dict with documents, rerank_applied, rerank_cache_hit, and latency.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        return {
            "documents": [],
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "latency_stages": {**latency_stages, "rerank": elapsed},
        }

    try:
        reranked_docs, rerank_applied, rerank_cache_hit = await perform_rerank(
            query, documents, cache=cache, reranker=reranker, top_k=top_k
        )
        if not rerank_applied:
            # No reranker path: sort and trim here
            reranked_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]
    except Exception:
        logger.exception("rerank: ColBERT failed, falling back to score sort")
        reranked_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]
        rerank_applied = False
        rerank_cache_hit = False

    if len(reranked_docs) >= 3:
        top_scores = [float(doc.get("score", 0.0)) for doc in reranked_docs[:3]]
        lead_gap = detect_score_gap(top_scores[:2])
        tail_gap = detect_score_gap(top_scores[1:3])
        if not bool(lead_gap["confident"]) and bool(tail_gap["confident"]):
            reranked_docs = reranked_docs[:2]

    elapsed = time.perf_counter() - t0
    logger.info(
        "rerank: %d → %d docs, applied=%s cache_hit=%s (%.3fs)",
        len(documents),
        len(reranked_docs),
        rerank_applied,
        rerank_cache_hit,
        elapsed,
    )
    return {
        "documents": reranked_docs,
        "rerank_applied": rerank_applied,
        "rerank_cache_hit": rerank_cache_hit,
        "latency_stages": {**latency_stages, "rerank": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 5: Rewrite query
# ---------------------------------------------------------------------------


async def _rewrite_query(
    query: str,
    rewrite_count: int,
    *,
    llm: Any | None = None,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rewrite user query for better retrieval.

    Returns dict with rewritten_query, rewrite_count, rewrite_effective, and latency.
    """
    t0 = time.perf_counter()
    topic_hint = get_query_topic_hint(query)
    expanded_query = expand_short_query(
        query,
        topic_hint=topic_hint.value if topic_hint is not None else None,
    )
    if expanded_query != query:
        elapsed = time.perf_counter() - t0
        logger.info(
            "rewrite: deterministic expansion '%s' → '%s' (%.3fs)",
            query,
            expanded_query,
            elapsed,
        )
        return {
            "rewritten_query": expanded_query,
            "rewrite_count": rewrite_count + 1,
            "rewrite_effective": True,
            "rewrite_provider_model": "deterministic_short_query_expansion",
            "latency_stages": {**latency_stages, "rewrite": elapsed},
        }

    try:
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()
        rewritten, effective, rewrite_actual_model = await rewrite_query_via_llm(query, llm=llm)
    except Exception:
        logger.exception("rewrite: LLM rewrite failed, keeping original query")
        rewritten = query
        effective = False
        rewrite_actual_model = "fallback"

    elapsed = time.perf_counter() - t0
    logger.info(
        "rewrite: attempt %d, '%.50s' → '%.50s' (%.3fs)",
        rewrite_count + 1,
        query,
        rewritten,
        elapsed,
    )

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count + 1,
        "rewrite_effective": effective,
        "rewrite_provider_model": rewrite_actual_model,
        "latency_stages": {**latency_stages, "rewrite": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 6: Cache store (see cache_stage.py)
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
    state_contract: PreAgentStateContract | None = None,
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
    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()

    # cache_key: use original user query for semantic cache so repeated queries hit
    # even when the agent reformulates them. Falls back to query when not provided.
    cache_key = original_query or query

    latency_stages: dict[str, float] = {}
    rewrite_count = 0
    rewrite_effective = True
    grade_confidence = 0.0
    current_query = query
    query_embedding: list[float] | None = None
    contract_topic_hint = state_contract.get("topic_hint") if state_contract is not None else None
    contract_filters = state_contract.get("filters") if state_contract is not None else None
    topic_hint = contract_topic_hint or get_query_topic_hint(query)
    semantic_cache_prechecked = semantic_cache_already_checked
    semantic_cache_filter_signature = resolve_semantic_cache_signature(
        filters=contract_filters if isinstance(contract_filters, dict) else None
    )
    semantic_cache_filter_sensitive = (
        detect_filter_sensitive_query(cache_key).is_filter_sensitive
        if semantic_cache_filter_signature is None
        else True
    )
    if semantic_cache_filter_sensitive and semantic_cache_filter_signature is None:
        semantic_cache_prechecked = True

    # Step 1: Cache check (use cache_key = original user query)
    # Pass pre_computed_embedding when caller already computed it (avoids redundant BGE-M3 call).
    cache_result: dict[str, Any]
    if (
        state_contract is not None
        and state_contract.get("cache_checked") is True
        and state_contract.get("cache_hit") is False
        and state_contract.get("embedding_bundle_ready") is True
    ):
        semantic_cache_prechecked = True
        cache_result = {
            "cache_hit": False,
            "cached_response": None,
            "query_embedding": state_contract.get("dense_vector"),
            "sparse_embedding": state_contract.get("sparse_vector"),
            "embeddings_cache_hit": False,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": state_contract.get("colbert_query"),
            "latency_stages": latency_stages,
        }
    else:
        cache_result = await _cache_check(
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
    semantic_cache_already_checked = semantic_cache_prechecked
    # Embedding of cache_key — kept separately for _cache_store so rewrites don't overwrite it
    cache_embedding = cast(list[float] | None, cache_result.get("query_embedding"))
    cache_sparse: Any = cache_result.get("sparse_embedding")
    latency_stages = cast(dict[str, float], cache_result["latency_stages"])
    colbert_query = cast(list[list[float]] | None, cache_result.get("colbert_query"))
    embeddings_cache_hit = bool(cache_result.get("embeddings_cache_hit", False))

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
            # Step 4: Rerank (if needed)
            rerank_from_retrieve = retrieve_result.get("rerank_applied", False)
            if grade_result["skip_rerank"] or rerank_from_retrieve:
                # High confidence or server-side ColBERT already applied — skip rerank
                final_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[
                    : config.rerank_top_k
                ]
                rerank_applied = rerank_from_retrieve  # preserve True from ColBERT path
                rerank_cache_hit = False
            else:
                rerank_result = await _rerank(
                    current_query,
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
            final_gap_confident = bool(final_gap["confident"])
            gap_ratio = final_gap.get("ratio", 0.0)
            # Only trim when gap is confident AND we have more than min floor.
            if final_gap_confident and len(final_docs) > _CONFIDENT_TRIM_TOP_K:
                logger.info(
                    "Score gap confident, trimming final docs",
                    extra={
                        "gap_ratio": gap_ratio,
                        "before_count": len(final_docs),
                        "after_count": _CONFIDENT_TRIM_TOP_K,
                    },
                )
                final_docs = final_docs[:_CONFIDENT_TRIM_TOP_K]

            # Small-to-big context expansion
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
                score_gap_confident=final_gap_confident,
            )
            result["skip_rewrite"] = skip_rewrite
            result["semantic_cache_already_checked"] = semantic_cache_already_checked
            return result

        # Check if we should rewrite
        can_rewrite = (
            rewrite_count < config.max_rewrite_attempts
            and not skip_rewrite
            and rewrite_effective
            and grade_result.get("score_improved", True)
        )
        if not can_rewrite:
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

    # Fallback: ran out of rewrites, return best docs with rerank
    rerank_from_retrieve = retrieve_result.get("rerank_applied", False)
    if rerank_from_retrieve:
        # Server-side ColBERT already applied — skip separate rerank
        final_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[
            :_DEFAULT_RERANK_TOP_K
        ]
        rerank_applied = True
        rerank_cache_hit = False
    else:
        rerank_result = await _rerank(
            current_query,
            documents,
            cache=cache,
            reranker=reranker,
            latency_stages=latency_stages,
        )
        latency_stages = rerank_result["latency_stages"]
        final_docs = rerank_result["documents"]
        rerank_applied = rerank_result["rerank_applied"]
        rerank_cache_hit = rerank_result["rerank_cache_hit"]
    final_gap = detect_score_gap(
        [doc.get("score", 0.0) for doc in final_docs if isinstance(doc, dict)]
    )
    final_gap_confident = bool(final_gap["confident"])
    gap_ratio = final_gap.get("ratio", 0.0)
    if final_gap_confident and len(final_docs) > _CONFIDENT_TRIM_TOP_K:
        logger.info(
            "Score gap confident, trimming final docs (fallback)",
            extra={
                "gap_ratio": gap_ratio,
                "before_count": len(final_docs),
                "after_count": _CONFIDENT_TRIM_TOP_K,
            },
        )
        final_docs = final_docs[:_CONFIDENT_TRIM_TOP_K]

    # Small-to-big context expansion (fallback path)
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
        score_gap_confident=final_gap_confident,
    )
    result["skip_rewrite"] = skip_rewrite
    result["semantic_cache_already_checked"] = semantic_cache_already_checked
    return result


async def _expand_small_to_big(
    final_docs: list[dict[str, Any]],
    *,
    qdrant: Any,
    config: Any,
) -> None:
    """Expand final_docs in-place with neighbor chunks via Small-to-Big service.

    Fetches window_before/window_after sibling chunks per doc from the same
    Qdrant document, replaces each doc's ``text`` with expanded context.
    Failures are logged but never crash the pipeline.
    """
    from telegram_bot.services.small_to_big import (
        SmallToBigMode,
        SmallToBigService,
    )

    if config.small_to_big_mode == SmallToBigMode.OFF or not final_docs:
        return
    try:
        stb = SmallToBigService(
            client=qdrant.client,
            collection_name=qdrant.collection_name,
            max_expanded_chunks=config.max_expanded_chunks,
            max_context_tokens=config.max_context_tokens,
        )
        expanded = await stb.expand_context(
            chunks=final_docs,
            window_before=config.small_to_big_window_before,
            window_after=config.small_to_big_window_after,
            deduplicate=True,
        )
        if expanded:
            for i, ec in enumerate(expanded):
                if i < len(final_docs):
                    final_docs[i]["text"] = ec.expanded_text
                    final_docs[i]["_expanded"] = True
            logger.debug("Small-to-big expanded %d chunks", len(expanded))
    except Exception as e:
        logger.warning("Small-to-big expansion failed: %s", e, exc_info=True)


def _assemble_context(
    *,
    query: str,
    original_query: str,
    documents: list[dict[str, Any]],
    latency_stages: dict[str, float],
    cache_hit: bool,
    embeddings_cache_hit: bool,
    search_cache_hit: bool,
    search_results_count: int,
    rerank_applied: bool,
    rerank_cache_hit: bool,
    grade_confidence: float,
    rewrite_count: int,
    query_type: str,
    query_embedding: list[float] | None,
    cache_key_embedding: list[float] | None,
    retrieved_context: list[dict[str, Any]],
    retrieval_backend_error: bool = False,
    retrieval_error_type: str | None = None,
    topic_hint: str | None = None,
    score_gap_confident: bool | None = None,
) -> dict[str, Any]:
    """Assemble context dict from pipeline results."""
    return {
        "documents": documents,
        "query": query,
        "original_query": original_query,
        "cache_hit": cache_hit,
        "embeddings_cache_hit": embeddings_cache_hit,
        "search_cache_hit": search_cache_hit,
        "search_results_count": search_results_count,
        "rerank_applied": rerank_applied,
        "rerank_cache_hit": rerank_cache_hit,
        "grade_confidence": grade_confidence,
        "rewrite_count": rewrite_count,
        "query_type": query_type,
        "query_embedding": query_embedding,
        "cache_key_embedding": cache_key_embedding,
        "latency_stages": latency_stages,
        "retrieved_context": retrieved_context,
        "retrieval_backend_error": retrieval_backend_error,
        "retrieval_error_type": retrieval_error_type,
        "topic_hint": topic_hint,
        "score_gap_confident": score_gap_confident,
        "embedding_error": False,
        "embedding_error_type": None,
    }
