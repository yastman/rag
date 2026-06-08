"""Core assistant public entrypoint."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from src.core.contracts import (
    AssistantError,
    AssistantRequest,
    AssistantResult,
    CoreDependencies,
    CrmAction,
    UserContext,
)
from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline
from src.utils.product_events import log_event


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

    request = AssistantRequest(
        query=query,
        collection=collection,
        user_context=user_context or UserContext(),
        request_id=rid,
    )
    result = await run_assistant_pipeline(request, dependencies=dependencies)

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
    "AssistantRequest",
    "AssistantResult",
    "CoreDependencies",
    "CrmAction",
    "UserContext",
    "run_assistant_request",
]
