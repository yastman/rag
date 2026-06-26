"""Score stubs — tracing removed (#2844)."""

from __future__ import annotations

from typing import Any


def compute_checkpointer_overhead_proxy_ms(result: dict[str, Any], ainvoke_wall_ms: float) -> float:
    """Compute proxy for checkpointer overhead."""
    stages_ms = sum(float(v) * 1000 for v in result.get("latency_stages", {}).values())
    return max(0.0, ainvoke_wall_ms - stages_ms)


def score(lf: Any, trace_id: str, *, name: str, value: Any, **kwargs: Any) -> None:
    """No-op stub — tracing removed (#2844)."""


def write_scores(lf: Any, result: dict, *, trace_id: str = "") -> None:
    """No-op stub — tracing removed (#2844)."""


def write_history_scores(
    lf: Any,
    trace_id: str,
    *,
    count: int = 0,
    latency_ms: float = 0.0,
    backend: str = "qdrant",
) -> None:
    """No-op stub — tracing removed (#2844)."""
