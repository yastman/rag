"""Runtime assistant orchestration pipeline."""

from __future__ import annotations

import time
from typing import Any

from src.core.contracts import (
    AssistantRequest,
    AssistantResult,
    CoreDependencies,
    UserContext,
)
from src.core.telemetry import emit_product_event
from src.retrieval.topic_classifier import get_query_topic_hint
from src.runtime.generation import GenerationRequest, generate_answer
from src.runtime.grounding.policy import get_grounding_mode
from src.runtime.pipeline.rag import rag_pipeline


async def run_assistant_pipeline(
    request: AssistantRequest,
    *,
    dependencies: CoreDependencies,
) -> AssistantResult:
    """Execute the live assistant path and return the public core result."""

    started = time.perf_counter()
    rid = request.request_id
    ctx = request.user_context or UserContext()

    try:
        from src.runtime.graph.nodes.classify import classify_query

        request_type = classify_query(request.query)
        state_contract: dict[str, Any] | None = {"filters": ctx.filters} if ctx.filters else None

        rag_result = await rag_pipeline(
            query=request.query,
            user_id=_coerce_user_id(ctx.user_id),
            session_id=ctx.session_id or rid,
            query_type=request_type,
            original_query=request.query,
            cache=dependencies.cache,
            embeddings=dependencies.embeddings,
            sparse_embeddings=dependencies.sparse_embeddings,
            qdrant=dependencies.qdrant,
            reranker=dependencies.reranker,
            llm=dependencies.llm,
            agent_role=ctx.role,
            state_contract=state_contract,
        )

        documents = _as_document_list(rag_result.get("documents"))
        retrieved_doc_ids = _extract_doc_ids(documents)
        emit_product_event(
            dependencies.telemetry,
            "search_completed",
            request_id=rid,
            route="cache_hit" if rag_result.get("cache_hit") else "rag_search",
            request_type=request_type,
            retrieved_doc_ids=retrieved_doc_ids,
            latency_ms=_latency_ms(started),
            error_type=None,
        )

        if rag_result.get("cache_hit"):
            return AssistantResult(
                response_text=str(rag_result.get("response", "") or ""),
                route="cache_hit",
                request_type=str(rag_result.get("query_type") or request_type),
                retrieved_doc_ids=retrieved_doc_ids,
                retrieved_sources=_extract_sources(documents),
                documents_count=len(documents),
                latency_ms=_latency_ms(started),
                request_id=rid,
                cache_hit=True,
                rerank_applied=bool(rag_result.get("rerank_applied", False)),
            )

        topic_hint = get_query_topic_hint(request.query)
        grounding_mode = get_grounding_mode(query_type=request_type, topic_hint=topic_hint)
        grade_confidence = rag_result.get("grade_confidence")

        generation = await generate_answer(
            GenerationRequest(
                query=request.query,
                documents=documents,
                grounding_mode=grounding_mode,
                grade_confidence=grade_confidence,
                config=dependencies.config,
            ),
        )
        generation_result = generation.payload
        usage = _as_usage_dict(generation_result.get("usage_details"))
        llm_model = _extract_llm_model(generation_result)

        emit_product_event(
            dependencies.telemetry,
            "llm_completed",
            request_id=rid,
            route="rag_search",
            request_type=request_type,
            latency_ms=_latency_ms(started),
            error_type=None,
            llm_model=llm_model,
            input_tokens=usage.get("input"),
            output_tokens=usage.get("output"),
        )

        return AssistantResult(
            response_text=generation.response_text,
            route="rag_search",
            request_type=str(rag_result.get("query_type") or request_type),
            retrieved_doc_ids=retrieved_doc_ids,
            retrieved_sources=_extract_sources(documents),
            documents_count=len(documents),
            latency_ms=_latency_ms(started),
            error_type=None,
            request_id=rid,
            cache_hit=False,
            llm_model=llm_model,
            llm_call_count=1,
            rerank_applied=bool(rag_result.get("rerank_applied", False)),
        )
    except Exception as exc:
        result = AssistantResult(
            response_text="Сервис временно недоступен. Пожалуйста, повторите через минуту.",
            route="error",
            request_type="",
            latency_ms=_latency_ms(started),
            error_type="dependency_failed",
            error_message=str(exc),
            request_id=rid,
        )
        emit_product_event(
            dependencies.telemetry,
            "dependency_failed",
            request_id=rid,
            route=result.route,
            request_type=result.request_type,
            latency_ms=result.latency_ms,
            error_type=result.error_type,
        )
        return result


def _latency_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _coerce_user_id(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_document_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_doc_ids(documents: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for doc in documents:
        meta_val = doc.get("metadata")
        metadata = meta_val if isinstance(meta_val, dict) else {}
        candidate = (
            metadata.get("source_id")
            or metadata.get("doc_id")
            or metadata.get("id")
            or doc.get("source_id")
            or doc.get("doc_id")
            or doc.get("id")
        )
        if candidate is not None:
            ids.append(str(candidate))
    return ids


def _extract_sources(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for doc in documents:
        meta_val = doc.get("metadata")
        metadata = meta_val if isinstance(meta_val, dict) else {}
        source: dict[str, str] = {}
        title = metadata.get("title") or metadata.get("source") or doc.get("title")
        url = metadata.get("url") or doc.get("url")
        if title is not None:
            source["title"] = str(title)
        if url is not None:
            source["url"] = str(url)
        if source:
            sources.append(source)
    return sources


def _as_usage_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_llm_model(generation_result: dict[str, Any]) -> str | None:
    model = generation_result.get("llm_provider_model") or generation_result.get("model")
    return str(model) if model else None


__all__ = ["run_assistant_pipeline"]
