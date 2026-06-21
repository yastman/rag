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

"""Core assistant public entrypoint."""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

from src.core.contracts import (
    AssistantError,
    AssistantRequest,
    AssistantResult,
    CoreDependencies,
    UserContext,
)
from src.core.telemetry import emit_product_event
from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline


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
    started = time.perf_counter()

    telemetry = dependencies.telemetry if dependencies is not None else None
    emit_product_event(telemetry, "assistant_request_started", request_id=rid, route="unknown")

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

        emit_product_event(
            telemetry,
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
    try:
        result = await run_assistant_pipeline(request, dependencies=dependencies)
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "run_assistant_request: unhandled exception for request_id=%s", rid
        )
        result = AssistantResult(
            response_text="Сервис временно недоступен. Пожалуйста, повторите через минуту.",
            route="error",
            request_type="",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type="dependency_failed",
            error_message=str(exc),
            request_id=rid,
        )

    emit_product_event(
        telemetry,
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
    "UserContext",
    "run_assistant_request",
]
