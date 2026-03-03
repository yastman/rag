"""Shared RAG core functions used by both agent SDK pipeline and LangGraph nodes.

Extracted to avoid ~300 LOC duplication between:
  telegram_bot/agents/rag_pipeline.py
  telegram_bot/graph/nodes/*.py

Core functions are pure computation (no Langfuse spans, no PipelineMetrics).
Adapters (pipeline / nodes) handle span tracking, metrics, and state wrapping.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any


logger = logging.getLogger(__name__)

_MAX_CONTEXT_SNIPPET = 500  # chars per doc for judge evaluation

# Query types eligible for semantic cache. Shared between agent SDK and LangGraph paths.
CACHEABLE_QUERY_TYPES: frozenset[str] = frozenset({"FAQ", "ENTITY", "STRUCTURED", "GENERAL"})

_REWRITE_PROMPT = (
    "Ты — помощник по поиску недвижимости. "
    "Пользователь задал вопрос, но результаты поиска оказались нерелевантными.\n\n"
    "Переформулируй запрос так, чтобы он лучше подходил для поиска по базе недвижимости.\n"
    "Верни ТОЛЬКО переформулированный запрос, без пояснений.\n\n"
    "Оригинальный запрос: {query}"
)


# ---------------------------------------------------------------------------
# H2: Context builder
# ---------------------------------------------------------------------------


def build_retrieved_context(
    results: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, str | float]]:
    """Build curated context snippets for LLM-as-a-Judge evaluation.

    Shared between rag_pipeline._build_retrieved_context and
    graph/nodes/retrieve._build_retrieved_context (identical logic).
    """
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


# ---------------------------------------------------------------------------
# H4: Query rewrite
# ---------------------------------------------------------------------------


async def rewrite_query_via_llm(
    query: str,
    *,
    llm: Any,
) -> tuple[str, bool, str]:
    """Call LLM to rewrite query for better retrieval.

    Args:
        query: The original query string.
        llm: LLM client (OpenAI-compatible: llm.chat.completions.create).

    Returns:
        Tuple of (rewritten_query, effective, model_name).
        - rewritten_query: reformulated query, or original if rewrite same
        - effective: True if the rewrite produced a different query
        - model_name: the model used for rewriting

    Raises:
        Exception: propagates LLM errors to caller (adapter handles fallback).
    """
    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()
    prompt = _REWRITE_PROMPT.format(query=query)
    response = await llm.chat.completions.create(
        model=config.rewrite_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=config.rewrite_max_tokens,
        name="rewrite-query",  # type: ignore[call-overload]  # langfuse kwarg
    )
    rewritten = (response.choices[0].message.content or "").strip()
    actual_model = getattr(response, "model", config.rewrite_model) or config.rewrite_model

    if not rewritten or rewritten == query:
        return (query, False, actual_model)
    return (rewritten, True, actual_model)


# ---------------------------------------------------------------------------
# H3: Rerank
# ---------------------------------------------------------------------------


async def perform_rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    cache: Any | None = None,
    reranker: Any | None = None,
    top_k: int,
) -> tuple[list[dict[str, Any]], bool, bool]:
    """Rerank documents using ColBERT reranker or return cache hit.

    Args:
        query: The query string for reranking.
        documents: Retrieved document dicts with "text" and "score" keys.
        cache: Optional cache instance with get_rerank_results / store_rerank_results.
        reranker: Optional ColBERT reranker instance with .rerank() method.
        top_k: Number of documents to return.

    Returns:
        Tuple of (reranked_docs, rerank_applied, rerank_cache_hit).
        - reranked_docs: the final list of documents
        - rerank_applied: True if ColBERT reranking was used
        - rerank_cache_hit: True if result came from cache

    Notes:
        Callers are responsible for Langfuse span tracking, PipelineMetrics,
        and fallback logic when reranker raises an exception.
        When no reranker is provided, returns all documents unmodified (no sort).
        Callers should sort/trim on the no-reranker path if needed.
    """
    if not documents:
        return ([], False, False)

    if reranker is not None:
        _cache_get = getattr(cache, "get_rerank_results", None) if cache is not None else None
        _cache_store = getattr(cache, "store_rerank_results", None) if cache is not None else None
        _has_get_rerank = callable(_cache_get) and asyncio.iscoroutinefunction(_cache_get)
        _has_store_rerank = callable(_cache_store) and asyncio.iscoroutinefunction(_cache_store)

        if _has_get_rerank and _cache_get is not None:
            cached_reranked = await _cache_get(query, documents, top_k)
            if cached_reranked is not None:
                return (cached_reranked, True, True)

        # May raise — callers handle error + fallback sort
        doc_texts = [doc.get("text", "") for doc in documents]
        rerank_results = await reranker.rerank(query=query, documents=doc_texts, top_k=top_k)

        reranked: list[dict[str, Any]] = []
        for rr in rerank_results:
            idx = rr["index"]
            if idx < len(documents):
                doc = {**documents[idx], "score": rr["score"]}
                reranked.append(doc)

        if _has_store_rerank and _cache_store is not None:
            await _cache_store(query, documents, top_k, reranked)

        return (reranked, True, False)

    # No reranker — return documents as-is; callers sort/trim as needed
    return (documents, False, False)


# ---------------------------------------------------------------------------
# H1: Embedding computation + semantic cache check
# ---------------------------------------------------------------------------


async def compute_query_embedding(
    query: str,
    *,
    cache: Any,
    embeddings: Any,
    pre_computed: list[float] | None = None,
    pre_computed_sparse: Any = None,
    pre_computed_colbert: list[list[float]] | None = None,
) -> tuple[list[float], Any, list[list[float]] | None, bool]:
    """Get or compute dense query embedding with optional sparse side-product.

    Handles three paths:
    1. Pre-computed: caller already has the embedding (e.g. agent pre-fetch) → return immediately.
    2. Redis cache hit: embedding stored from previous request → return with from_cache=True.
    3. Model compute: call embeddings.aembed_hybrid (preferred) or aembed_query, cache result.

    Args:
        query: The query string.
        cache: Cache instance with get_embedding / store_embedding / store_sparse_embedding.
        embeddings: Embedding model with aembed_hybrid or aembed_query.
        pre_computed: Pre-computed dense vector (bypasses all computation).
        pre_computed_sparse: Pre-computed sparse vector; returned alongside pre_computed.
        pre_computed_colbert: Pre-computed ColBERT vectors; returned alongside pre_computed.

    Returns:
        Tuple of (dense, sparse, colbert, from_cache).
        - dense: dense embedding vector (always present)
        - sparse: sparse vector if computed via hybrid or pre_computed_sparse; else None
        - colbert: pre_computed_colbert if provided; else None
          (ColBERT-after-miss fetching is the caller's responsibility)
        - from_cache: True if dense vector came from Redis cache

    Raises:
        Exception: propagates embedding model errors to caller (adapter handles fallback).
    """
    # Path 1: caller already has pre-computed vectors
    if pre_computed is not None:
        return (pre_computed, pre_computed_sparse, pre_computed_colbert, False)

    # Path 2: check Redis embedding cache
    dense = await cache.get_embedding(query)
    from_cache = dense is not None

    if dense is not None:
        return (dense, None, None, from_cache)

    # Path 3: compute via model
    _has_hybrid = callable(
        getattr(embeddings, "aembed_hybrid", None)
    ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid)

    if _has_hybrid:
        dense, sparse = await embeddings.aembed_hybrid(query)
        await cache.store_embedding(query, dense)
        await cache.store_sparse_embedding(query, sparse)
    else:
        dense = await embeddings.aembed_query(query)
        await cache.store_embedding(query, dense)
        sparse = None

    return (dense, sparse, None, False)


async def check_semantic_cache(
    query: str,
    vector: list[float],
    query_type: str,
    *,
    cache: Any,
    agent_role: str | None = None,
) -> tuple[bool, str | None]:
    """Check semantic cache for a given query vector.

    Only checks for query types in CACHEABLE_QUERY_TYPES.

    Args:
        query: The query string.
        vector: Dense embedding vector for semantic similarity lookup.
        query_type: Query type (e.g. "FAQ", "GENERAL"). Non-cacheable types skip check.
        cache: Cache instance with check_semantic method.
        agent_role: Optional role for role-gated cache scoping (agent SDK only).

    Returns:
        Tuple of (hit, response).
        - hit: True if a cached response was found
        - response: The cached response string, or None on miss
    """
    if query_type not in CACHEABLE_QUERY_TYPES:
        return (False, None)

    cached = await cache.check_semantic(
        query=query,
        vector=vector,
        query_type=query_type,
        cache_scope="rag",
        agent_role=agent_role,
    )

    if cached:
        return (True, cached)
    return (False, None)
