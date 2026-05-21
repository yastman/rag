"""Correlation context for cross-cutting observability."""

from __future__ import annotations

from typing import Any, TypedDict


class CorrelationContext(TypedDict, total=False):
    """Typed dict holding optional correlation fields for observability."""

    environment: str
    release: str
    service: str
    component: str
    event: str
    trace_id: str
    langfuse_trace_id: str
    request_id: str
    telegram_user_id_hash: str
    chat_id_hash: str
    tenant_id: str
    bot_instance_id: str
    deployment_id: str
    route: str
    pipeline_mode: str
    llm_model: str
    dependency_status: str
    error_type: str


def build_correlation_context(**kwargs: Any) -> dict[str, Any]:
    """Build a correlation context dict containing only non-None values."""
    return {k: v for k, v in kwargs.items() if v is not None}
