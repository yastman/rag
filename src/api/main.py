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
from fastapi.responses import JSONResponse

from src.api.schemas import QueryRequest, QueryResponse


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown pipeline services."""
    from telegram_bot.graph.config import GraphConfig
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.integrations.cache import CacheLayerManager
    from telegram_bot.services.colbert_reranker import ColbertRerankerService
    from telegram_bot.services.qdrant import QdrantService

    cfg = GraphConfig.from_env()

    cache = CacheLayerManager(
        redis_url=cfg.redis_url,
        cache_thresholds=cfg.cache_thresholds,
        cache_ttl=cfg.cache_ttl,
    )
    await cache.initialize()

    embeddings = cfg.create_embeddings()
    sparse_embeddings = cfg.create_sparse_embeddings()

    qdrant = QdrantService(
        url=cfg.qdrant_url,
        collection_name=cfg.qdrant_collection,
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=30,
    )

    reranker = None
    if cfg.rerank_provider == "colbert":
        reranker = ColbertRerankerService(base_url=cfg.bge_m3_url)
    elif cfg.rerank_provider != "none":
        logger.warning("Unknown RERANK_PROVIDER=%s, reranking disabled", cfg.rerank_provider)
    llm = cfg.create_llm()

    graph = build_graph(
        cache=cache,
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=reranker,
        llm=llm,
        message=None,
    )

    app.state.graph = graph
    app.state.cache = cache
    app.state.qdrant = qdrant
    app.state.embeddings = embeddings
    app.state.sparse_embeddings = sparse_embeddings
    app.state.max_rewrite_attempts = cfg.max_rewrite_attempts

    logger.info("RAG API services initialized")
    yield

    await cache.close()
    await qdrant.close()
    if hasattr(embeddings, "aclose"):
        await embeddings.aclose()
    if hasattr(sparse_embeddings, "aclose"):
        await sparse_embeddings.aclose()
    logger.info("RAG API services shutdown")


app = FastAPI(title="RAG API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def generic_error_handler(_request: Any, _exc: Exception) -> JSONResponse:
    """Return structured error response for unhandled exceptions."""
    logger.exception("Unhandled error in RAG API")
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
async def health() -> dict[str, str]:
    """Readiness probe."""
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """Run a RAG query through the LangGraph pipeline."""
    from telegram_bot.graph.state import make_initial_state
    from telegram_bot.observability import get_client, propagate_attributes
    from telegram_bot.scoring import write_langfuse_scores

    start = time.perf_counter()

    session_id = req.session_id or f"api-{req.user_id}"
    state = make_initial_state(
        user_id=req.user_id,
        session_id=session_id,
        query=req.query,
    )
    state["max_rewrite_attempts"] = int(getattr(app.state, "max_rewrite_attempts", 1))

    trace_kwargs: dict[str, Any] = {
        "session_id": session_id,
        "user_id": str(req.user_id),
        "tags": [req.channel, "rag"],
    }
    if req.langfuse_trace_id:
        trace_kwargs["trace_id"] = req.langfuse_trace_id

    with propagate_attributes(**trace_kwargs):
        result = await app.state.graph.ainvoke(state)
        lf = get_client()
        lf.update_current_trace(
            input=req.query,
            output=result.get("response", ""),
            metadata={
                "source": req.channel,
                "query_type": result.get("query_type", ""),
            },
        )
        # Set wall-time fields so write_langfuse_scores reports real latency
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["pipeline_wall_ms"] = elapsed_ms
        summarize_s = result.get("latency_stages", {}).get("summarize", 0)
        result["user_perceived_wall_ms"] = elapsed_ms - (summarize_s * 1000)

        # Write Langfuse scores for observability parity with bot
        write_langfuse_scores(lf, result)

    return QueryResponse(
        response=result.get("response", ""),
        query_type=result.get("query_type", ""),
        cache_hit=result.get("cache_hit", False),
        documents_count=result.get("search_results_count", 0),
        rerank_applied=result.get("rerank_applied", False),
        latency_ms=round(elapsed_ms, 1),
    )
