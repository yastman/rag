"""FastAPI RAG API — wrapper around LangGraph pipeline.

Exposes POST /query for synchronous RAG queries and GET /health for readiness.
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.errors import GraphRecursionError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas import QueryRequest, QueryResponse
from src.observability import observe
from src.observability_payloads import (
    build_safe_input_payload,
    build_safe_output_payload,
)


logger = logging.getLogger(__name__)
_LANGFUSE_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown pipeline services."""
    from src.runtime.graph.config import GraphConfig
    from src.runtime.services.qdrant import QdrantService
    from telegram_bot.graph.graph import build_graph
    from telegram_bot.integrations.cache import CacheLayerManager

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

    # Reranking is performed server-side by Qdrant via the ColBERT vector;
    # there is no per-process Python reranker to construct. We log the
    # configured path here so misconfiguration is visible at startup.
    if cfg.rerank_provider == "colbert":
        logger.info("Reranking via server-side Qdrant ColBERT path")
    elif cfg.rerank_provider != "none":
        logger.warning("Unknown RERANK_PROVIDER=%s, reranking disabled", cfg.rerank_provider)

    llm = cfg.create_llm()

    graph = build_graph(
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
    """Best-effort lookup of the current Langfuse trace id, with uuid fallback.

    Centralised here (#1236) so every exception handler emits the same
    ``trace_id`` envelope without duplicating the lookup logic.
    """
    try:
        from src.observability import get_client

        lf = get_client()
        if lf is not None:
            tid = lf.get_current_trace_id()
            if tid:
                return tid
    except Exception:
        logger.debug("Unable to resolve Langfuse trace id for RAG API error", exc_info=True)
    return uuid.uuid4().hex


# -----------------------------------------------------------------------------
# Exception handlers (#1236)
#
# FastAPI's documented error-handling pattern (see fastapi.tiangolo docs,
# "Handling Errors > Override the default exception handlers") is to register
# specific handlers *in addition to* a fallback ``Exception`` handler. The
# specific handlers take precedence over the blanket one, so:
#
#   * ``StarletteHTTPException`` keeps the proper status code and detail
#     message for ``HTTPException`` raised in code as well as Starlette's
#     internal HTTP errors (e.g. 404 from routing) instead of being squashed
#     to ``{"error": "internal_error"}`` 500.
#   * ``RequestValidationError`` keeps the 422 response shape with field-level
#     errors instead of being squashed to a generic 500.
#   * ``Exception`` remains the last-resort 500 fallback for genuinely
#     unhandled errors.
#
# All three handlers emit the same envelope shape ``{error, message, trace_id,
# recoverable, ...}`` so API clients can rely on a single error contract.
# -----------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Return the proper HTTP status code (401/403/404/...) instead of 500.

    Catches both ``fastapi.HTTPException`` (subclass of
    ``starlette.exceptions.HTTPException``) and Starlette-internal HTTP errors
    raised by routing/middleware.
    """
    trace_id = _resolve_trace_id()
    # 5xx are still errors; log them. 4xx are client problems; debug-level.
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
    """Return 422 with field-level details instead of being swallowed by the 500 fallback."""
    trace_id = _resolve_trace_id()
    logger.debug(
        "RequestValidationError in RAG API: %s",
        exc.errors(),
        extra={"trace_id": trace_id},
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
    """Return structured error response for unhandled exceptions.

    This is the *last-resort* fallback. ``HTTPException`` and
    ``RequestValidationError`` are caught by their specific handlers above
    and never reach this one (#1236).
    """
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
    """Readiness probe.

    Default: shallow check (``{"status": "ok"}``) for liveness probes — fast,
    no external dependencies, always 200 once the process is up.

    With ``?deep=true`` (#1236): probe every initialised dependency on
    ``app.state`` (cache, qdrant) and report their individual status. Returns
    HTTP 503 if any dependency is unhealthy so a Kubernetes readiness probe
    treats the pod as Not Ready until backends recover.
    """
    if not deep:
        return JSONResponse(status_code=200, content={"status": "ok"})

    components: dict[str, dict[str, Any]] = {}
    overall_ok = True

    # Cache (Redis) — issue a no-op ping if available; otherwise just verify
    # the layer was initialised. CacheLayerManager exposes .ping() in the
    # current implementation; fall back to attribute presence if not.
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

    # Qdrant — most clients expose .health() / .get_collections() async.
    # We pick whichever method exists, prefer .health() if defined.
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


def _normalize_langfuse_trace_id(trace_id: str | None) -> str | None:
    if not trace_id:
        return None
    if _LANGFUSE_TRACE_ID_RE.fullmatch(trace_id):
        return trace_id

    from src.observability import get_client

    lf = get_client()
    if lf is None:
        return None
    return lf.create_trace_id(seed=trace_id)


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """Run a RAG query through the LangGraph pipeline."""
    normalized_trace_id = _normalize_langfuse_trace_id(req.langfuse_trace_id)
    if normalized_trace_id:
        return await _query_with_explicit_trace(req, langfuse_trace_id=normalized_trace_id)
    return await _query_with_observability(req)


@observe(name="rag-api-query", capture_input=False, capture_output=False)
async def _query_with_observability(req: QueryRequest) -> QueryResponse:
    return await _execute_query(req)


async def _query_with_explicit_trace(
    req: QueryRequest,
    *,
    langfuse_trace_id: str,
) -> QueryResponse:
    from src.observability import get_client

    lf = get_client()
    if lf is None:
        return await _execute_query(req)

    with lf.start_as_current_observation(
        as_type="span",
        name="rag-api-query",
        trace_context=cast(Any, {"trace_id": langfuse_trace_id}),
    ):
        return await _execute_query(req)


async def _execute_query(req: QueryRequest) -> QueryResponse:
    """Run a RAG query through the LangGraph pipeline."""
    from src.observability import get_client, propagate_attributes
    from src.runtime.graph.state import make_initial_state
    from src.scoring import write_langfuse_scores

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
        "metadata": {"source": req.channel},
        "tags": ["api", "rag", req.channel],
    }

    with propagate_attributes(**trace_kwargs):
        try:
            result = await app.state.graph.ainvoke(state)
        except GraphRecursionError:
            elapsed_ms = (time.perf_counter() - start) * 1000
            fallback_response = (
                "Запрос слишком сложный — достигнут лимит обработки. Попробуйте упростить его."
            )
            lf = get_client()
            if lf is not None:
                lf.update_current_span(
                    input=build_safe_input_payload(
                        content_type="api", text=req.query, route="rag-api-query"
                    ),
                    output=build_safe_output_payload(
                        answer_text=fallback_response,
                        chunks_count=1,
                        fallback_reason="recursion_limit",
                    ),
                    metadata={
                        "source": req.channel,
                        "query_type": "ERROR",
                        "error_reason": "recursion_limit",
                    },
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
                write_langfuse_scores(lf, fallback_result)
            return QueryResponse(
                response=fallback_response,
                query_type="ERROR",
                cache_hit=False,
                documents_count=0,
                rerank_applied=False,
                latency_ms=round(elapsed_ms, 1),
                context=[],
            )

        lf = get_client()
        if lf is not None:
            lf.update_current_span(
                input=build_safe_input_payload(
                    content_type="api", text=req.query, route="rag-api-query"
                ),
                output=build_safe_output_payload(
                    answer_text=result.get("response", ""),
                    chunks_count=1,
                    sources_count=result.get("search_results_count", 0),
                ),
                metadata={
                    "source": req.channel,
                    "query_type": result.get("query_type", ""),
                },
            )
        # Set wall-time fields so write_langfuse_scores reports real latency
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["pipeline_wall_ms"] = elapsed_ms
        result["e2e_latency_ms"] = elapsed_ms
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
        context=result.get("retrieved_context", []),
    )
