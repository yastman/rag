"""Langfuse trace validation for E2E tests.

Validates that traces contain expected spans and scores after bot queries.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from langfuse import Langfuse


logger = logging.getLogger(__name__)

# Expected spans from observability implementation
EXPECTED_SPANS = {
    "telegram-message",
    "query-router",
    "cache-semantic-check",
    "voyage-embed-query",
    "qdrant-hybrid-search-rrf",
}

# Expected scores from bot handler
EXPECTED_SCORES = {
    "semantic_cache_hit",
    "query_type",
}


@dataclass(frozen=True)
class TraceValidationResult:
    """Result of trace validation."""

    ok: bool
    trace_id: str | None
    missing_spans: set[str]
    missing_scores: set[str]
    error: str | None = None

    def __str__(self) -> str:
        if self.ok:
            return f"OK (trace_id={self.trace_id})"
        if self.error:
            return f"FAIL: {self.error}"
        parts = []
        if self.missing_spans:
            parts.append(f"missing_spans={self.missing_spans}")
        if self.missing_scores:
            parts.append(f"missing_scores={self.missing_scores}")
        return f"FAIL (trace_id={self.trace_id}): {', '.join(parts)}"


def validate_latest_trace(
    *,
    started_at: datetime,
    langfuse: Langfuse | None = None,
) -> TraceValidationResult:
    """Validate the most recent trace has expected spans and scores.

    Args:
        started_at: When the test started (UTC). Traces older than this are ignored.
        langfuse: Optional Langfuse client. Uses default if not provided.

    Returns:
        TraceValidationResult with ok=True if all expected spans/scores found.
    """
    if langfuse is None:
        langfuse = Langfuse()

    try:
        # Query recent traces with telegram+rag tags
        traces_page = langfuse.api.trace.list(
            tags=["telegram", "rag"],
            from_timestamp=started_at - timedelta(seconds=5),
            order_by="timestamp.desc",
            limit=5,
        )

        if not traces_page.data:
            return TraceValidationResult(
                ok=False,
                trace_id=None,
                missing_spans=set(EXPECTED_SPANS),
                missing_scores=set(EXPECTED_SCORES),
                error="No traces found with tags ['telegram', 'rag']",
            )

        # Get the most recent trace
        trace_id = traces_page.data[0].id
        trace = langfuse.api.trace.get(trace_id)

        # Extract span names and score names
        span_names = {obs.name for obs in trace.observations if obs.name}
        score_names = {s.name for s in trace.scores if s.name}

        missing_spans = EXPECTED_SPANS - span_names
        missing_scores = EXPECTED_SCORES - score_names

        return TraceValidationResult(
            ok=(not missing_spans and not missing_scores),
            trace_id=trace_id,
            missing_spans=missing_spans,
            missing_scores=missing_scores,
        )

    except Exception as e:
        logger.exception("Error validating trace")
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(EXPECTED_SPANS),
            missing_scores=set(EXPECTED_SCORES),
            error=str(e),
        )


def is_validation_enabled() -> bool:
    """Check if E2E trace validation is enabled via environment variable."""
    return os.getenv("E2E_VALIDATE_LANGFUSE", "").lower() in ("1", "true", "yes")
