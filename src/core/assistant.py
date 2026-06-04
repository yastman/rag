"""Core assistant entrypoint contract (PR A skeleton).

The module intentionally defines a narrow, synchronous-import-safe contract:

- lightweight data containers (`UserContext`, `AssistantResult`, `CrmAction`)
- recoverable core result model
- thin async entrypoint `run_assistant_request()` that preserves caller API without
  touching live integrations
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from src.utils.product_events import log_event


@dataclass
class UserContext:
    """Minimal user/session context for core assistant request handling."""

    user_id: str = ""
    session_id: str = ""
    role: str = "client"
    filters: dict[str, Any] | None = None
    language: str = "ru"


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
) -> AssistantResult:
    """Execute a single assistant request in skeleton mode.

    This implementation is intentionally minimal: it validates input shape, emits
    product events, and returns a recoverable error result without invoking live
    integrations.
    """

    _ = (query, collection, user_context)
    rid = request_id or str(uuid4())

    log_event("assistant_request_started", request_id=rid)
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


__all__ = [
    "AssistantError",
    "AssistantResult",
    "CrmAction",
    "UserContext",
    "run_assistant_request",
]
