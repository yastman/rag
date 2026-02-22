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

import asyncio
import hashlib
import logging
import time
from typing import Any

from telegram_bot.graph.nodes.cache import CACHEABLE_QUERY_TYPES
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

_MAX_CONTEXT_SNIPPET = 500  # chars per doc for judge evaluation
_REWRITE_PROMPT = (
    "Ты — помощник по поиску недвижимости. "
    "Пользователь задал вопрос, но результаты поиска оказались нерелевантными.\n\n"
    "Переформулируй запрос так, чтобы он лучше подходил для поиска по базе недвижимости.\n"
    "Верни ТОЛЬКО переформулированный запрос, без пояснений.\n\n"
    "Оригинальный запрос: {query}"
)
_DEFAULT_RERANK_TOP_K = 5


# ---------------------------------------------------------------------------
# Step 1: Cache check
# ---------------------------------------------------------------------------


@observe(name="cache-check", capture_input=False, capture_output=False)
async def _cache_check(
    query: str,
    query_type: str,
    user_id: int,
    *,
    cache: Any,
    embeddings: Any,
    latency_stages: dict[str, float],
    agent_role: str | None = None,
    pre_computed_embedding: list[float] | None = None,
) -> dict[str, Any]:
    """Compute embedding and check semantic cache.

    Returns dict with cache_hit, cached_response, query_embedding, and latency.
    """
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "query_type": query_type,
        }
    )

    start = time.perf_counter()

    # Step 1: Get or compute dense embedding (prefer hybrid for efficiency)
    # If caller pre-computed the embedding (pre-agent cache check), reuse it directly.
    embedding_error: bool = False
    embedding_error_type: str | None = None
    colbert_query: list[list[float]] | None = None

    if pre_computed_embedding:
        logger.debug(
            "_cache_check: reusing pre-computed embedding (%d dims)", len(pre_computed_embedding)
        )
        embedding = pre_computed_embedding
        embeddings_cache_hit = False  # embedding came from caller, not Redis
        # Still warm the embedding cache so downstream hits benefit
        await cache.store_embedding(query, embedding)
    else:
        embedding = await cache.get_embedding(query)
        embeddings_cache_hit = embedding is not None

    if embedding is None:
        try:
            _has_hybrid_colbert = callable(
                getattr(embeddings, "aembed_hybrid_with_colbert", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)
            _has_hybrid = callable(
                getattr(embeddings, "aembed_hybrid", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid)
            if _has_hybrid_colbert:
                embedding, sparse, colbert_query = await embeddings.aembed_hybrid_with_colbert(
                    query
                )
                await cache.store_embedding(query, embedding)
                await cache.store_sparse_embedding(query, sparse)
            elif _has_hybrid:
                embedding, sparse = await embeddings.aembed_hybrid(query)
                await cache.store_embedding(query, embedding)
                await cache.store_sparse_embedding(query, sparse)
            else:
                embedding = await embeddings.aembed_query(query)
                await cache.store_embedding(query, embedding)
        except Exception as exc:
            embedding_error = True
            embedding_error_type = type(exc).__name__
            logger.error("Embedding failed: %s: %s", embedding_error_type, exc)
            latency = time.perf_counter() - start
            lf.update_current_span(
                level="ERROR",
                output={
                    "embedding_error": True,
                    "embedding_error_type": embedding_error_type,
                    "error_message": str(exc)[:200],
                    "duration_ms": round(latency * 1000, 1),
                },
            )
            return {
                "cache_hit": False,
                "cached_response": None,
                "query_embedding": None,
                "embeddings_cache_hit": False,
                "embedding_error": True,
                "embedding_error_type": embedding_error_type,
                "error_response": "Сервис временно недоступен. Пожалуйста, повторите через минуту.",
                "colbert_query": None,
                "latency_stages": {**latency_stages, "cache_check": latency},
            }

    # Step 2: Check semantic cache (allowlisted types only)
    cached = None
    if query_type in CACHEABLE_QUERY_TYPES:
        cached = await cache.check_semantic(
            query=query,
            vector=embedding,
            query_type=query_type,
            cache_scope="rag",
            agent_role=agent_role,
        )

    latency = time.perf_counter() - start

    if cached:
        logger.info("cache_check HIT (%.3fs, type=%s)", latency, query_type)
        lf.update_current_span(
            output={
                "cache_hit": True,
                "embeddings_cache_hit": embeddings_cache_hit,
                "hit_layer": "semantic",
                "duration_ms": round(latency * 1000, 1),
            }
        )
        return {
            "cache_hit": True,
            "cached_response": cached,
            "query_embedding": embedding,
            "embeddings_cache_hit": embeddings_cache_hit,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": colbert_query,
            "latency_stages": {**latency_stages, "cache_check": latency},
        }

    logger.info("cache_check MISS (%.3fs, type=%s)", latency, query_type)
    lf.update_current_span(
        output={
            "cache_hit": False,
            "embeddings_cache_hit": embeddings_cache_hit,
            "hit_layer": "none",
            "duration_ms": round(latency * 1000, 1),
        }
    )
    return {
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": embedding,
        "embeddings_cache_hit": embeddings_cache_hit,
        "embedding_error": embedding_error,
        "embedding_error_type": embedding_error_type,
        "colbert_query": colbert_query,
        "latency_stages": {**latency_stages, "cache_check": latency},
    }


# ---------------------------------------------------------------------------
# Step 2: Hybrid retrieve
# ---------------------------------------------------------------------------


def _build_retrieved_context(
    results: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, str | float]]:
    """Build curated context snippets for LLM-as-a-Judge evaluation."""
    ctx: list[dict[str, str | float]] = []
    for doc in results[:limit]:
        if not isinstance(doc, dict):
            continue
        text = doc.get("text", "")
        meta = doc.get("metadata", {})
        ctx.append(
            {
                "content": text[:_MAX_CONTEXT_SNIPPET],
                "score": doc.get("score", 0),
                "chunk_location": meta.get("chunk_location", ""),
            }
        )
    return ctx


@observe(name="hybrid-retrieve", capture_input=False, capture_output=False)
async def _hybrid_retrieve(
    query: str,
    query_embedding: list[float] | None,
    *,
    cache: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    embeddings: Any | None = None,
    colbert_query: list[list[float]] | None = None,
    top_k: int = 20,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Retrieve documents via hybrid RRF search with caching.

    Returns dict with documents, search_results_count, sparse_embedding, and latency.
    """
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "top_k": top_k,
        }
    )

    dense_vector = query_embedding
    sparse_vector: Any = None

    # After rewrite, query_embedding is None — re-embed the rewritten query
    if dense_vector is None and embeddings is not None:
        dense_vector = await cache.get_embedding(query)
        if dense_vector is None:
            sparse_cached = await cache.get_sparse_embedding(query)
            if sparse_cached is not None:
                dense_vector = await embeddings.aembed_query(query)
                await cache.store_embedding(query, dense_vector)
                sparse_vector = sparse_cached
            elif callable(
                getattr(embeddings, "aembed_hybrid_with_colbert", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert):
                (
                    dense_vector,
                    sparse_vector,
                    colbert_query,
                ) = await embeddings.aembed_hybrid_with_colbert(query)
                await cache.store_embedding(query, dense_vector)
                await cache.store_sparse_embedding(query, sparse_vector)
            elif callable(
                getattr(embeddings, "aembed_hybrid", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid):
                dense_vector, sparse_vector = await embeddings.aembed_hybrid(query)
                await cache.store_embedding(query, dense_vector)
                await cache.store_sparse_embedding(query, sparse_vector)
            else:

                async def _get_dense() -> list[float]:
                    vec: list[float] = await embeddings.aembed_query(query)
                    await cache.store_embedding(query, vec)
                    return vec

                async def _get_sparse() -> Any:
                    vec = await sparse_embeddings.aembed_query(query)
                    await cache.store_sparse_embedding(query, vec)
                    return vec

                dense_vector, sparse_vector = await asyncio.gather(_get_dense(), _get_sparse())

    if not dense_vector:
        dense_vector = []

    start = time.perf_counter()

    # Step 1: Check search cache
    cached_results = await cache.get_search_results(dense_vector)
    if cached_results is not None:
        latency = time.perf_counter() - start
        logger.info("retrieve HIT search cache (%.3fs, %d docs)", latency, len(cached_results))
        cached_ctx = _build_retrieved_context(cached_results)
        lf.update_current_span(
            output={
                "results_count": len(cached_results),
                "search_cache_hit": True,
                "duration_ms": round(latency * 1000, 1),
                "eval_query": query[:2000],
                "eval_docs": "\n\n".join(
                    f"[{d.get('score', 0):.2f}] {str(d.get('content', ''))[:500]}"
                    for d in cached_ctx
                ),
            }
        )
        return {
            "documents": cached_results,
            "search_results_count": len(cached_results),
            "search_cache_hit": True,
            "query_embedding": dense_vector,
            "latency_stages": {**latency_stages, "retrieve": latency},
            "retrieval_backend_error": False,
            "retrieval_error_type": None,
            "retrieved_context": cached_ctx,
            "rerank_applied": False,
            "colbert_query": colbert_query,
        }

    # Step 2: Get sparse embedding (cached or compute)
    if sparse_vector is None:
        sparse_vector = await cache.get_sparse_embedding(query)
        if sparse_vector is None:
            sparse_vector = await sparse_embeddings.aembed_query(query)
            await cache.store_sparse_embedding(query, sparse_vector)

    # Step 3: Hybrid search via Qdrant SDK (RRF fusion or ColBERT server-side rerank)
    _has_colbert_search = callable(getattr(qdrant, "hybrid_search_rrf_colbert", None))
    colbert_search_used = False
    if colbert_query and _has_colbert_search:
        qdrant_result = await qdrant.hybrid_search_rrf_colbert(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            top_k=top_k,
            return_meta=True,
        )
        colbert_search_used = True
    else:
        qdrant_result = await qdrant.hybrid_search_rrf(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            top_k=top_k,
            return_meta=True,
        )
    if isinstance(qdrant_result, tuple) and len(qdrant_result) == 2:
        results, search_meta = qdrant_result
    else:
        results = qdrant_result
        search_meta = {"backend_error": False, "error_type": None, "error_message": None}

    # Step 4: Cache results
    if results and not search_meta.get("backend_error", False):
        await cache.store_search_results(dense_vector, None, results)

    latency = time.perf_counter() - start
    logger.info("retrieve done (%.3fs, %d docs)", latency, len(results))

    scores = [d.get("score", 0) for d in results if isinstance(d, dict)]
    result_ctx = _build_retrieved_context(results)
    lf.update_current_span(
        output={
            "results_count": len(results),
            "top_score": round(scores[0], 4) if scores else None,
            "min_score": round(scores[-1], 4) if scores else None,
            "search_cache_hit": False,
            "retrieval_backend_error": search_meta.get("backend_error", False),
            "retrieval_error_type": search_meta.get("error_type"),
            "duration_ms": round(latency * 1000, 1),
            "eval_query": query[:2000],
            "eval_docs": "\n\n".join(
                f"[{d.get('score', 0):.2f}] {str(d.get('content', ''))[:500]}" for d in result_ctx
            ),
        }
    )

    return {
        "documents": results,
        "search_results_count": len(results),
        "search_cache_hit": False,
        "sparse_embedding": sparse_vector,
        "query_embedding": dense_vector or None,
        "latency_stages": {**latency_stages, "retrieve": latency},
        "retrieval_backend_error": search_meta.get("backend_error", False),
        "retrieval_error_type": search_meta.get("error_type"),
        "retrieved_context": result_ctx,
        "rerank_applied": colbert_search_used,
        "colbert_query": colbert_query,
    }


# ---------------------------------------------------------------------------
# Step 3: Grade documents
# ---------------------------------------------------------------------------


@observe(name="grade-documents")
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

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "score_improved": score_improved,
        "latency_stages": {**latency_stages, "grade": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 4: Rerank
# ---------------------------------------------------------------------------


@observe(name="rerank")
async def _rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    reranker: Any | None = None,
    top_k: int = _DEFAULT_RERANK_TOP_K,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rerank documents using ColBERT or score-based fallback.

    Returns dict with documents, rerank_applied, and latency.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        return {
            "documents": [],
            "rerank_applied": False,
            "latency_stages": {**latency_stages, "rerank": elapsed},
        }

    if reranker is not None:
        try:
            doc_texts = [doc.get("text", "") for doc in documents]
            rerank_results = await reranker.rerank(query=query, documents=doc_texts, top_k=top_k)

            reranked: list[dict[str, Any]] = []
            for rr in rerank_results:
                idx = rr["index"]
                if idx < len(documents):
                    doc = {**documents[idx], "score": rr["score"]}
                    reranked.append(doc)

            elapsed = time.perf_counter() - t0
            logger.info(
                "rerank: ColBERT reranked %d → %d docs (%.3fs)",
                len(documents),
                len(reranked),
                elapsed,
            )
            return {
                "documents": reranked,
                "rerank_applied": True,
                "latency_stages": {**latency_stages, "rerank": elapsed},
            }
        except Exception as e:
            logger.exception("rerank: ColBERT failed, falling back to score sort")
            get_client().update_current_span(
                level="ERROR",
                status_message=f"ColBERT rerank failed: {str(e)[:200]}",
            )

    # Fallback: sort by existing score, take top-k
    sorted_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]

    elapsed = time.perf_counter() - t0
    logger.info(
        "rerank: score-based sort %d → %d docs (%.3fs)",
        len(documents),
        len(sorted_docs),
        elapsed,
    )
    return {
        "documents": sorted_docs,
        "rerank_applied": False,
        "latency_stages": {**latency_stages, "rerank": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 5: Rewrite query
# ---------------------------------------------------------------------------


@observe(name="query-rewrite")
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

    try:
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()

        prompt = _REWRITE_PROMPT.format(query=query)
        response = await llm.chat.completions.create(
            model=config.rewrite_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=config.rewrite_max_tokens,
            name="rewrite-query",  # type: ignore[call-overload]
        )
        rewritten = (response.choices[0].message.content or "").strip()
        rewrite_actual_model = (
            getattr(response, "model", config.rewrite_model) or config.rewrite_model
        )

        if not rewritten or rewritten == query:
            rewritten = query
            effective = False
        else:
            effective = True
    except Exception as e:
        logger.exception("rewrite: LLM rewrite failed, keeping original query")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"Rewrite LLM failed: {str(e)[:200]}",
        )
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
# Step 6: Cache store
# ---------------------------------------------------------------------------


@observe(name="cache-store", capture_input=False, capture_output=False)
async def _cache_store(
    query: str,
    response: str,
    query_embedding: list[float] | None,
    query_type: str,
    user_id: int,
    *,
    cache: Any,
    search_results_count: int = 0,
    latency_stages: dict[str, float],
    agent_role: str | None = None,
) -> dict[str, Any]:
    """Store response in semantic cache (allowlisted types only).

    Returns dict with latency update.
    """
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "response_length": len(response),
            "search_results_count": search_results_count,
        }
    )
    start = time.perf_counter()

    stored_semantic = False
    if response and query_embedding:
        if query_type in CACHEABLE_QUERY_TYPES:
            await cache.store_semantic(
                query=query,
                response=response,
                vector=query_embedding,
                query_type=query_type,
                cache_scope="rag",
                agent_role=agent_role,
            )
            stored_semantic = True

        if stored_semantic:
            logger.info("cache_store: stored=semantic (type=%s)", query_type)

    latency = time.perf_counter() - start
    lf.update_current_span(
        output={
            "stored": stored_semantic,
            "stored_semantic": stored_semantic,
            "duration_ms": round(latency * 1000, 1),
        }
    )

    return {
        "stored_semantic": stored_semantic,
        "latency_stages": {**latency_stages, "cache_store": latency},
    }


# ---------------------------------------------------------------------------
# Orchestrator: rag_pipeline()
# ---------------------------------------------------------------------------


@observe(name="rag-pipeline", capture_input=False, capture_output=False)
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
    pre_computed_embedding: list[float] | None = None,
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

    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "original_query_preview": cache_key[:120] if cache_key != query else None,
            "user_id": user_id,
            "session_id": session_id,
            "query_type": query_type,
        }
    )

    latency_stages: dict[str, float] = {}
    rewrite_count = 0
    rewrite_effective = True
    grade_confidence = 0.0
    current_query = query
    query_embedding: list[float] | None = None

    # Step 1: Cache check (use cache_key = original user query)
    # Pass pre_computed_embedding when caller already computed it (avoids redundant BGE-M3 call).
    cache_result = await _cache_check(
        cache_key,
        query_type,
        user_id,
        cache=cache,
        embeddings=embeddings,
        latency_stages=latency_stages,
        agent_role=agent_role,
        pre_computed_embedding=pre_computed_embedding,
    )
    # Embedding of cache_key — kept separately for _cache_store so rewrites don't overwrite it
    cache_embedding: list[float] | None = cache_result.get("query_embedding")
    latency_stages = cache_result["latency_stages"]
    colbert_query: list[list[float]] | None = cache_result.get("colbert_query")

    if cache_result.get("embedding_error"):
        return {
            "response": cache_result.get("error_response", ""),
            "cache_hit": False,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": False,
            "embedding_error": True,
            "embedding_error_type": cache_result.get("embedding_error_type"),
            "latency_stages": latency_stages,
            "rewrite_count": 0,
            "query_type": query_type,
            "retrieved_context": [],
        }

    if cache_result["cache_hit"]:
        return {
            "response": cache_result["cached_response"],
            "cache_hit": True,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": cache_result["embeddings_cache_hit"],
            "embedding_error": False,
            "embedding_error_type": None,
            "latency_stages": latency_stages,
            "rewrite_count": 0,
            "query_type": query_type,
            "retrieved_context": [],
        }

    # For retrieval, use reformulated query embedding.
    # If cache_key differs from query (agent reformulated), pre-fetch the
    # reformulated query embedding for the FIRST retrieval attempt. This avoids a
    # redundant BGE-M3 call in _hybrid_retrieve on warm requests (#513).
    # Subsequent iterations after _rewrite_query set query_embedding = None and
    # let _hybrid_retrieve handle cache lookup for those new rewritten queries.
    if cache_key != query:
        query_embedding = await cache.get_embedding(query)
    else:
        query_embedding = cache_embedding

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
                    :_DEFAULT_RERANK_TOP_K
                ]
                rerank_applied = rerank_from_retrieve  # preserve True from ColBERT path
            else:
                rerank_result = await _rerank(
                    current_query,
                    documents,
                    reranker=reranker,
                    latency_stages=latency_stages,
                )
                latency_stages = rerank_result["latency_stages"]
                final_docs = rerank_result["documents"]
                rerank_applied = rerank_result["rerank_applied"]

            result = _assemble_context(
                query=current_query,
                original_query=query,
                documents=final_docs,
                latency_stages=latency_stages,
                cache_hit=False,
                embeddings_cache_hit=cache_result["embeddings_cache_hit"],
                search_cache_hit=retrieve_result.get("search_cache_hit", False),
                search_results_count=retrieve_result["search_results_count"],
                rerank_applied=rerank_applied,
                grade_confidence=grade_confidence,
                rewrite_count=rewrite_count,
                query_type=query_type,
                query_embedding=query_embedding,
                cache_key_embedding=cache_embedding,
                retrieved_context=retrieve_result.get("retrieved_context", []),
                retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
                retrieval_error_type=retrieve_result.get("retrieval_error_type"),
            )
            result["skip_rewrite"] = skip_rewrite
            lf.update_current_span(
                output={
                    "cache_hit": False,
                    "documents_count": len(final_docs),
                    "rerank_applied": rerank_applied,
                    "rewrite_count": rewrite_count,
                }
            )
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
        query_embedding = None  # Force re-embed on next retrieve
        colbert_query = None  # Force re-encode ColBERT on next retrieve

    # Fallback: ran out of rewrites, return best docs with rerank
    rerank_from_retrieve = retrieve_result.get("rerank_applied", False)
    if rerank_from_retrieve:
        # Server-side ColBERT already applied — skip separate rerank
        final_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[
            :_DEFAULT_RERANK_TOP_K
        ]
        rerank_applied = True
    else:
        rerank_result = await _rerank(
            current_query,
            documents,
            reranker=reranker,
            latency_stages=latency_stages,
        )
        latency_stages = rerank_result["latency_stages"]
        final_docs = rerank_result["documents"]
        rerank_applied = rerank_result["rerank_applied"]

    result = _assemble_context(
        query=current_query,
        original_query=query,
        documents=final_docs,
        latency_stages=latency_stages,
        cache_hit=False,
        embeddings_cache_hit=cache_result["embeddings_cache_hit"],
        search_cache_hit=retrieve_result.get("search_cache_hit", False),
        search_results_count=retrieve_result["search_results_count"],
        rerank_applied=rerank_applied,
        grade_confidence=grade_confidence,
        rewrite_count=rewrite_count,
        query_type=query_type,
        query_embedding=query_embedding,
        cache_key_embedding=cache_embedding,
        retrieved_context=retrieve_result.get("retrieved_context", []),
        retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
        retrieval_error_type=retrieve_result.get("retrieval_error_type"),
    )
    result["skip_rewrite"] = skip_rewrite
    lf.update_current_span(
        output={
            "cache_hit": False,
            "documents_count": len(final_docs),
            "rerank_applied": rerank_applied,
            "rewrite_count": rewrite_count,
            "fallback": True,
        }
    )
    return result


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
    grade_confidence: float,
    rewrite_count: int,
    query_type: str,
    query_embedding: list[float] | None,
    cache_key_embedding: list[float] | None,
    retrieved_context: list[dict[str, Any]],
    retrieval_backend_error: bool = False,
    retrieval_error_type: str | None = None,
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
        "grade_confidence": grade_confidence,
        "rewrite_count": rewrite_count,
        "query_type": query_type,
        "query_embedding": query_embedding,
        "cache_key_embedding": cache_key_embedding,
        "latency_stages": latency_stages,
        "retrieved_context": retrieved_context,
        "retrieval_backend_error": retrieval_backend_error,
        "retrieval_error_type": retrieval_error_type,
        "embedding_error": False,
        "embedding_error_type": None,
    }
