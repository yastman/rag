"""FastAPI RAG API — wrapper around LangGraph pipeline.

Exposes POST /query for synchronous RAG queries and GET /health for readiness.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.errors import GraphRecursionError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas import QueryRequest, QueryResponse


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown pipeline services."""
    from src.runtime.graph.builder import build_pipeline
    from src.runtime.graph.config import GraphConfig
    from src.runtime.integrations.cache import CacheLayerManager
    from src.runtime.services.qdrant import QdrantService

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

    if cfg.rerank_provider == "colbert":
        logger.info("Reranking via server-side Qdrant ColBERT path")
    elif cfg.rerank_provider != "none":
        logger.warning("Unknown RERANK_PROVIDER=%s, reranking disabled", cfg.rerank_provider)

    llm = cfg.create_llm()

    graph = build_pipeline(
        cache=cache,
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=None,
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


def _resolve_trace_id() -> str:
    return uuid.uuid4().hex


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    trace_id = _resolve_trace_id()
    if exc.status_code >= 500:
        logger.error(
            "HTTPException %s in RAG API: %s",
            exc.status_code,
            exc.detail,
            extra={"trace_id": trace_id},
        )
    else:
        logger.debug(
            "HTTPException %s in RAG API: %s",
            exc.status_code,
            exc.detail,
            extra={"trace_id": trace_id},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": str(exc.detail) if exc.detail is not None else "",
            "status_code": exc.status_code,
            "trace_id": trace_id,
            "recoverable": exc.status_code < 500,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    trace_id = _resolve_trace_id()
    logger.debug(
        "RequestValidationError in RAG API: %s", exc.errors(), extra={"trace_id": trace_id}
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": exc.errors(),
            "trace_id": trace_id,
            "recoverable": True,
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(_request: Any, _exc: Exception) -> JSONResponse:
    trace_id = _resolve_trace_id()
    logger.exception("Unhandled error in RAG API", extra={"trace_id": trace_id})
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Internal server error",
            "trace_id": trace_id,
            "recoverable": False,
        },
    )


@app.get("/health")
async def health(deep: bool = False) -> JSONResponse:
    """Readiness probe."""
    if not deep:
        return JSONResponse(status_code=200, content={"status": "ok"})

    components: dict[str, dict[str, Any]] = {}
    overall_ok = True

    cache = getattr(app.state, "cache", None)
    if cache is None:
        components["cache"] = {"status": "uninitialized"}
        overall_ok = False
    else:
        try:
            ping = getattr(cache, "ping", None)
            if callable(ping):
                pong = ping()
                if hasattr(pong, "__await__"):
                    pong = await pong
                components["cache"] = {"status": "ok" if pong else "degraded"}
                if not pong:
                    overall_ok = False
            else:
                components["cache"] = {"status": "ok"}
        except Exception as exc:
            components["cache"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

    qdrant = getattr(app.state, "qdrant", None)
    if qdrant is None:
        components["qdrant"] = {"status": "uninitialized"}
        overall_ok = False
    else:
        try:
            probe = getattr(qdrant, "health", None) or getattr(qdrant, "get_collections", None)
            if callable(probe):
                result = probe()
                if hasattr(result, "__await__"):
                    await result
                components["qdrant"] = {"status": "ok"}
            else:
                components["qdrant"] = {"status": "ok"}
        except Exception as exc:
            components["qdrant"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

    return JSONResponse(
        status_code=200 if overall_ok else 503,
        content={
            "status": "ok" if overall_ok else "degraded",
            "components": components,
        },
    )


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """Run a RAG query through the LangGraph pipeline."""
    return await _execute_query(req)


async def _execute_query(req: QueryRequest) -> QueryResponse:
    """Run a RAG query through the LangGraph pipeline."""
    from src.runtime.graph.state import make_initial_state
    from src.scoring import write_pipeline_scores

    start = time.perf_counter()

    session_id = req.session_id or f"api-{req.user_id}"
    state = make_initial_state(
        user_id=req.user_id,
        session_id=session_id,
        query=req.query,
    )
    state["max_rewrite_attempts"] = int(getattr(app.state, "max_rewrite_attempts", 1))

    try:
        result = await app.state.graph.ainvoke(state)
    except GraphRecursionError:
        elapsed_ms = (time.perf_counter() - start) * 1000
        fallback_response = (
            "Запрос слишком сложный — достигнут лимит обработки. Попробуйте упростить его."
        )
        fallback_result: dict[str, Any] = {
            "input_type": "api",
            "query_type": "ERROR",
            "pipeline_wall_ms": elapsed_ms,
            "e2e_latency_ms": elapsed_ms,
            "user_perceived_wall_ms": elapsed_ms,
            "cache_hit": False,
            "search_results_count": 0,
            "rerank_applied": False,
            "response": fallback_response,
        }
        write_pipeline_scores(None, fallback_result)
        return QueryResponse(
            response=fallback_response,
            query_type="ERROR",
            cache_hit=False,
            documents_count=0,
            rerank_applied=False,
            latency_ms=round(elapsed_ms, 1),
            context=[],
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    result["pipeline_wall_ms"] = elapsed_ms
    result["e2e_latency_ms"] = elapsed_ms
    summarize_s = result.get("latency_stages", {}).get("summarize", 0)
    result["user_perceived_wall_ms"] = elapsed_ms - (summarize_s * 1000)

    write_pipeline_scores(None, result)

    return QueryResponse(
        response=result.get("response", ""),
        query_type=result.get("query_type", ""),
        cache_hit=result.get("cache_hit", False),
        documents_count=result.get("search_results_count", 0),
        rerank_applied=result.get("rerank_applied", False),
        latency_ms=round(elapsed_ms, 1),
        context=result.get("retrieved_context", []),
    )
