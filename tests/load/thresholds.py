# tests/load/thresholds.py
"""P95 latency thresholds for load tests."""

from dataclasses import dataclass


@dataclass
class Thresholds:
    """Warn and fail thresholds in milliseconds."""

    warn_ms: int
    fail_ms: int


# Component-level thresholds
THRESHOLDS = {
    "routing": Thresholds(warn_ms=20, fail_ms=30),
    "cache_hit": Thresholds(warn_ms=20, fail_ms=30),
    "qdrant": Thresholds(warn_ms=120, fail_ms=200),
    "full_rag": Thresholds(warn_ms=3000, fail_ms=4000),
    # TTFT only checked if actually measured (streaming enabled)
    "ttft": Thresholds(warn_ms=800, fail_ms=1200),
}

# Regression threshold (fail if p95 > baseline * 1.20)
REGRESSION_THRESHOLD = 1.20

# Minimum cache hit rate
MIN_CACHE_HIT_RATE = 0.60
