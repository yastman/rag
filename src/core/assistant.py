"""Core assistant entrypoint contract (PR A skeleton).

The module intentionally defines a narrow, synchronous-import-safe contract:

- lightweight data containers (`UserContext`, `AssistantResult`, `CrmAction`)
- recoverable core result model
- thin async entrypoint `run_assistant_request()` that preserves caller API without
  touching live integrations
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from src.utils.product_events import log_event


if TYPE_CHECKING:
    from telegram_bot.pipelines.state_contract import PreAgentStateContract


@dataclass
class UserContext:
    """Minimal user/session context for core assistant request handling."""

    user_id: str = ""
    session_id: str = ""
    role: str = "client"
    filters: dict[str, Any] | None = None
    language: str = "ru"


@dataclass
class CoreDependencies:
    """Runtime collaborators required to execute the existing RAG path."""

    cache: Any
    embeddings: Any
    sparse_embeddings: Any
    qdrant: Any
    reranker: Any | None = None
    llm: Any | None = None
    config: Any | None = None


@dataclass
class CrmAction:
    """Intent for a proposed CRM action, awaiting explicit confirmation."""

    action_type: str
    payload: dict[str, Any]
    summary: str


@dataclass
class AssistantResult:
    """Structured response object returned by the assistant core entrypoint."""

    response_text: str
    route: str = ""
    request_type: str = ""
    retrieved_doc_ids: list[str] = field(default_factory=list)
    retrieved_sources: list[dict[str, str]] = field(default_factory=list)
    documents_count: int = 0
    latency_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    proposed_crm_action: CrmAction | None = None
    request_id: str = ""
    cache_hit: bool = False
    llm_model: str | None = None
    llm_call_count: int = 0
    rerank_applied: bool = False


class AssistantError(RuntimeError):
    """Unrecoverable error from the core assistant."""

    def __init__(self, message: str, *, error_type: str = "internal") -> None:
        super().__init__(message)
        self.error_type = error_type


async def run_assistant_request(
    query: str,
    *,
    collection: str,
    user_context: UserContext | None = None,
    request_id: str | None = None,
    dependencies: CoreDependencies | None = None,
) -> AssistantResult:
    """Execute a single assistant request through the core assistant entrypoint.

    Without explicit dependencies this stays in skeleton mode so tests and
    import-only callers do not touch live integrations.
    """

    _ = collection
    rid = request_id or str(uuid4())

    log_event("assistant_request_started", request_id=rid, route="unknown")

    if dependencies is None:
        await asyncio.sleep(0)

        result = AssistantResult(
            response_text="Assistant execution is not available in the current skeleton.",
            route="error",
            request_type="",
            request_id=rid,
            error_type="service_unavailable",
            error_message="Assistant core is in skeleton mode and does not execute live services.",
        )

        log_event(
            "assistant_request_completed",
            request_id=result.request_id,
            route=result.route,
            request_type=result.request_type,
            error_type=result.error_type,
            latency_ms=result.latency_ms,
        )

        return result

    started = time.perf_counter()
    ctx = user_context or UserContext()

    try:
        from src.runtime.graph.nodes.classify import classify_query
        from telegram_bot.agents.rag_pipeline import rag_pipeline
        from telegram_bot.services.generate_response import generate_response

        request_type = classify_query(query)
        state_contract: PreAgentStateContract | None = (
            cast("PreAgentStateContract", {"filters": ctx.filters}) if ctx.filters else None
        )

        rag_result = await rag_pipeline(
            query=query,
            user_id=_coerce_user_id(ctx.user_id),
            session_id=ctx.session_id or rid,
            query_type=request_type,
            original_query=query,
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
        search_latency_ms = _latency_ms(started)
        log_event(
            "search_completed",
            request_id=rid,
            route="cache_hit" if rag_result.get("cache_hit") else "rag_search",
            request_type=request_type,
            retrieved_doc_ids=retrieved_doc_ids,
            latency_ms=search_latency_ms,
            error_type=None,
        )

        if rag_result.get("cache_hit"):
            result = AssistantResult(
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
        else:
            generation_kwargs: dict[str, Any] = {
                "query": query,
                "documents": documents,
            }
            if dependencies.config is not None:
                generation_kwargs["config"] = dependencies.config
            generation_result = await generate_response(**generation_kwargs)
            usage = _as_usage_dict(generation_result.get("usage_details"))
            llm_model = _extract_llm_model(generation_result)

            log_event(
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

            result = AssistantResult(
                response_text=str(generation_result.get("response", "") or ""),
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
        log_event(
            "dependency_failed",
            request_id=rid,
            route=result.route,
            request_type=result.request_type,
            latency_ms=result.latency_ms,
            error_type=result.error_type,
        )

    log_event(
        "assistant_request_completed",
        request_id=result.request_id,
        route=result.route,
        request_type=result.request_type,
        error_type=result.error_type,
        latency_ms=result.latency_ms,
    )

    return result


def _coerce_user_id(user_id: str) -> int:
    """Return an integer user id for the existing Telegram RAG pipeline."""
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return 0


def _latency_ms(started: float) -> float:
    """Return elapsed wall-clock milliseconds rounded for stable logs/tests."""
    return round((time.perf_counter() - started) * 1000, 3)


def _as_document_list(value: Any) -> list[dict[str, Any]]:
    """Normalize existing RAG document output to a list of dictionaries."""
    if not isinstance(value, list):
        return []
    return [doc for doc in value if isinstance(doc, dict)]


def _metadata_for(document: dict[str, Any]) -> dict[str, Any]:
    """Return document metadata if present."""
    metadata = document.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _extract_doc_ids(documents: list[dict[str, Any]]) -> list[str]:
    """Extract stable source ids used by golden-case checks."""
    ids: list[str] = []
    for document in documents:
        metadata = _metadata_for(document)
        doc_id = (
            metadata.get("source_id")
            or metadata.get("doc_id")
            or metadata.get("id")
            or document.get("source_id")
            or document.get("doc_id")
            or document.get("id")
        )
        if doc_id is not None:
            ids.append(str(doc_id))
    return ids


def _extract_sources(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract title/url source metadata for adapters."""
    sources: list[dict[str, str]] = []
    for document in documents:
        metadata = _metadata_for(document)
        source: dict[str, str] = {}
        title = metadata.get("title") or document.get("title")
        url = metadata.get("url") or document.get("url")
        if title is not None:
            source["title"] = str(title)
        if url is not None:
            source["url"] = str(url)
        if source:
            sources.append(source)
    return sources


def _as_usage_dict(value: Any) -> dict[str, Any]:
    """Return usage details from generate_response() when available."""
    return value if isinstance(value, dict) else {}


def _extract_llm_model(generation_result: dict[str, Any]) -> str | None:
    """Extract the provider model name from generation metadata."""
    model = generation_result.get("llm_provider_model") or generation_result.get("model")
    return str(model) if model else None


__all__ = [
    "AssistantError",
    "AssistantResult",
    "CoreDependencies",
    "CrmAction",
    "UserContext",
    "run_assistant_request",
]
