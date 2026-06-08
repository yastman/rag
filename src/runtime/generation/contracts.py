"""Runtime generation request/result contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerationRequest:
    """Core generation request, independent from Telegram message rendering."""

    query: str
    documents: list[dict[str, Any]]
    retrieved_context: list[dict[str, Any]] | None = None
    raw_messages: list[Any] | None = None
    latency_stages: dict[str, float] | None = None
    llm_call_count: int = 0
    grounding_mode: str = "normal"
    grade_confidence: float | None = None
    config: Any | None = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """Normalized generation result returned by the runtime generation seam."""

    payload: dict[str, Any]

    @property
    def response_text(self) -> str:
        return str(self.payload.get("response", "") or "")


GenerationCallable = Callable[..., Awaitable[dict[str, Any]]]


__all__ = ["GenerationCallable", "GenerationRequest", "GenerationResult"]
