"""FastAPI RAG API — wrapper around LangGraph pipeline.

Exposes POST /query for synchronous RAG queries and GET /health for readiness.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.api.schemas import QueryRequest, QueryResponse


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown pipeline services."""
    from telegram_bot.graph.config import GraphConfig
    from telegram_bot.integrations.cache import CacheLayerManager
    from telegram_bot.services.colbert_reranker import ColbertRerankerService
    from telegram_bot.services.qdrant import QdrantService

    cfg = GraphConfig.from_env()

    cache = CacheLayerManager(
        redis_url=cfg.redis_url,
        cache_thresholds=cfg.cache_thresholds,
        cache_ttl=cfg.cache_ttl,
    )
    await cache.connect()

    embeddings = cfg.create_embeddings()
    sparse_embeddings = cfg.create_sparse_embeddings()

    qdrant = QdrantService(
        url=cfg.qdrant_url,
        collection_name=cfg.qdrant_collection,
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=30,
    )

    reranker = ColbertRerankerService(base_url=cfg.bge_m3_url)
    llm = cfg.create_llm()

    app.state.config = cfg
    app.state.cache = cache
    app.state.embeddings = embeddings
    app.state.sparse_embeddings = sparse_embeddings
    app.state.qdrant = qdrant
    app.state.reranker = reranker
    app.state.llm = llm

    logger.info("RAG API services initialized")
    yield

    await cache.close()
    logger.info("RAG API services shutdown")


app = FastAPI(title="RAG API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Readiness probe."""
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """Run a RAG query through the LangGraph pipeline."""
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.graph.state import make_initial_state
    from telegram_bot.observability import get_client, propagate_attributes

    start = time.perf_counter()

    session_id = req.session_id or f"api-{req.user_id}"
    state = make_initial_state(
        user_id=req.user_id,
        session_id=session_id,
        query=req.query,
    )

    graph = build_graph(
        cache=app.state.cache,
        embeddings=app.state.embeddings,
        sparse_embeddings=app.state.sparse_embeddings,
        qdrant=app.state.qdrant,
        reranker=app.state.reranker,
        llm=app.state.llm,
        message=None,
    )

    trace_kwargs: dict[str, Any] = {
        "session_id": session_id,
        "user_id": str(req.user_id),
        "tags": ["api", "rag"],
    }
    if req.langfuse_trace_id:
        trace_kwargs["trace_id"] = req.langfuse_trace_id

    with propagate_attributes(**trace_kwargs):
        result = await graph.ainvoke(state)
        lf = get_client()
        lf.update_current_trace(
            input=req.query,
            output=result.get("response", ""),
            metadata={"source": "api", "query_type": result.get("query_type", "")},
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return QueryResponse(
        response=result.get("response", ""),
        query_type=result.get("query_type", ""),
        cache_hit=result.get("cache_hit", False),
        documents_count=result.get("search_results_count", 0),
        rerank_applied=result.get("rerank_applied", False),
        latency_ms=round(elapsed_ms, 1),
    )
