"""Langfuse trace validation for Telethon E2E runs.

Used by `scripts/e2e/runner.py` when `E2E_VALIDATE_LANGFUSE=1`.
Validation is done via Langfuse SDK v3 API client (Langfuse().api.trace.list/get).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from langfuse import Langfuse


DEFAULT_TRACE_NAME = "telegram-rag-query"
DEFAULT_TAGS = ["telegram", "rag"]

SCORE_NAMES = {
    "query_type",
    "latency_total_ms",
    "semantic_cache_hit",
    "embeddings_cache_hit",
    "search_cache_hit",
    "rerank_applied",
    "rerank_cache_hit",
    "results_count",
    "no_results",
    "llm_used",
}


@dataclass(frozen=True)
class TraceValidationResult:
    ok: bool
    trace_id: str | None
    missing_spans: set[str]
    missing_scores: set[str]
    error: str | None = None


def _langfuse_is_configured() -> bool:
    # Langfuse SDK can be configured via env. If keys are missing, validation is meaningless.
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def is_validation_enabled() -> bool:
    """True when E2E should validate Langfuse traces."""
    return os.getenv("E2E_VALIDATE_LANGFUSE", "0").lower() in {"1", "true", "yes"}


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) >= 0.5
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes", "y"}:
            return True
        if lower in {"0", "false", "no", "n"}:
            return False
    return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def wait_for_trace(
    *,
    started_at: datetime,
    timeout_s: float = 15.0,
    poll_interval_s: float = 0.5,
    trace_name: str = DEFAULT_TRACE_NAME,
    tags: list[str] | None = DEFAULT_TAGS,
) -> str | None:
    """Poll Langfuse until a recent trace exists, returning trace_id."""
    if not _langfuse_is_configured():
        return None

    langfuse = Langfuse()
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        traces_page = langfuse.api.trace.list(
            name=trace_name,
            tags=tags,
            from_timestamp=started_at - timedelta(seconds=5),
            order_by="timestamp.desc",
            limit=5,
        )
        if traces_page.data:
            return traces_page.data[0].id

        time.sleep(poll_interval_s)

    return None


def validate_latest_trace(
    *,
    started_at: datetime,
    should_skip_rag: bool,
    is_command: bool,
    timeout_s: float = 15.0,
    poll_interval_s: float = 0.5,
    trace_name: str = DEFAULT_TRACE_NAME,
    tags: list[str] | None = DEFAULT_TAGS,
) -> TraceValidationResult:
    """Validate that the latest trace contains required spans/scores."""
    if is_command:
        # Commands are handled by separate handlers, not the RAG pipeline entrypoint.
        return TraceValidationResult(
            ok=True,
            trace_id=None,
            missing_spans=set(),
            missing_scores=set(),
        )

    # Base contract: all "real" bot messages should emit these scores.
    # This enables branch-aware validation without flakiness from cache hits.
    required_scores: set[str] = set(SCORE_NAMES)

    # Base span contract (real names from this repository)
    required_spans: set[str] = {"telegram-message", "query-router"}

    if not _langfuse_is_configured():
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(required_spans),
            missing_scores=set(required_scores),
            error="Langfuse keys are not configured (LANGFUSE_PUBLIC_KEY/SECRET_KEY).",
        )

    trace_id = wait_for_trace(
        started_at=started_at,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        trace_name=trace_name,
        tags=tags,
    )
    if not trace_id:
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(required_spans),
            missing_scores=set(required_scores),
            error="No matching trace found in Langfuse within timeout.",
        )

    langfuse = Langfuse()
    trace = langfuse.api.trace.get(trace_id)

    span_names = {obs.name for obs in trace.observations}
    scores = {s.name: getattr(s, "value", None) for s in trace.scores}
    score_names = set(scores.keys())

    # Determine branch from scores, falling back to scenario hints when scores are missing.
    query_type = _as_float(scores.get("query_type"))
    semantic_hit = _as_bool(scores.get("semantic_cache_hit"))
    llm_used = _as_bool(scores.get("llm_used"))
    results_count = _as_float(scores.get("results_count"))
    no_results = _as_bool(scores.get("no_results"))
    embeddings_hit = _as_bool(scores.get("embeddings_cache_hit"))
    search_hit = _as_bool(scores.get("search_cache_hit"))
    rerank_applied = _as_bool(scores.get("rerank_applied"))
    rerank_hit = _as_bool(scores.get("rerank_cache_hit"))

    # If query_type missing, infer CHITCHAT from scenario hint.
    is_chitchat = (query_type == 0.0) if query_type is not None else bool(should_skip_rag)

    if not is_chitchat:
        required_spans |= {"cache-semantic-check"}

    if not is_chitchat and semantic_hit is False:
        required_spans |= {"cache-search-check"}

        if embeddings_hit is False:
            required_spans |= {"voyage-embed-query"}

        if search_hit is False:
            required_spans |= {"qdrant-hybrid-search-rrf"}

        if rerank_applied is True:
            required_spans |= {"cache-rerank-check"}
            if rerank_hit is False:
                required_spans |= {"voyage-rerank"}

        if (llm_used is True) and (no_results is False) and ((results_count or 0) > 0):
            required_spans |= {"cache-semantic-store"}

    missing_spans = set(required_spans - span_names)
    missing_scores = set(required_scores - score_names)

    return TraceValidationResult(
        ok=(not missing_spans and not missing_scores),
        trace_id=trace_id,
        missing_spans=missing_spans,
        missing_scores=missing_scores,
    )
