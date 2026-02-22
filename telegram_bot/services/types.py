"""Shared result types for pipeline services."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result of client pipeline execution."""

    answer: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    query_type: str = "GENERAL"
    cache_hit: bool = False
    needs_agent: bool = False  ***REMOVED*** fallback signal for bot.py
    agent_intent: str = ""  ***REMOVED*** set by dedicated intent gate (not classify_query)
    latency_ms: float = 0.0
    llm_call_count: int = 0
    scores: dict[str, float] = field(default_factory=dict)
    pipeline_mode: str = "client_direct"
    sent_message: dict[str, int] | None = None  ***REMOVED*** {"chat_id": ..., "message_id": ...}
    response_sent: bool = False  ***REMOVED*** True if streaming already delivered
