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
from src.runtime.pipeline.context import PipelineContext
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
        from src.runtime.routing.classify import classify_query

        request_type = classify_query(request.query)
        state_contract: PipelineContext | None = (
            PipelineContext(filters=ctx.filters) if ctx.filters else None
        )

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
        grounded = generation_result.get("grounded")
        llm_calls = generation_result.get("llm_call_count")

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
            llm_call_count=(
                llm_calls
                if isinstance(llm_calls, int) and not isinstance(llm_calls, bool) and llm_calls >= 0
                else 1
            ),
            rerank_applied=bool(rag_result.get("rerank_applied", False)),
            grounding_mode=grounding_mode,
            grounded=grounded if isinstance(grounded, bool) else None,
            safe_fallback_used=bool(generation_result.get("safe_fallback_used", False)),
            usage=_coerce_usage(usage),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "assistant_pipeline: unhandled exception for request_id=%s", rid
        )
        raise


def _latency_ms(started: float) -> float:
    """Calculate elapsed time in milliseconds since a start point."""
    return round((time.perf_counter() - started) * 1000, 3)


def _coerce_user_id(value: str) -> int:
    """Convert a user ID string to integer, returning 0 on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_document_list(value: Any) -> list[dict[str, Any]]:
    """Safely extract a list of document dictionaries."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_doc_ids(documents: list[dict[str, Any]]) -> list[str]:
    """Extract document IDs from a list of document dictionaries."""
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
    """Extract source metadata (title and URL) from documents."""
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
    """Safely extract usage details as a dictionary."""
    return value if isinstance(value, dict) else {}


def _coerce_usage(value: Any) -> dict[str, int]:
    """Coerce provider usage details into an int-valued dict for the core boundary."""
    if not isinstance(value, dict):
        return {}
    usage: dict[str, int] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        usage[str(key)] = int(raw)
    return usage


def _extract_llm_model(generation_result: dict[str, Any]) -> str | None:
    """Extract the LLM model name from generation result metadata."""
    model = generation_result.get("llm_provider_model") or generation_result.get("model")
    return str(model) if model else None


__all__ = ["run_assistant_pipeline"]
