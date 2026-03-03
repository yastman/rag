"""Implicit retry detection via embedding similarity (#756).

Detects when a user reformulates a query — an implicit negative feedback signal.
If cosine_similarity(current, previous) > 0.7 AND time_delta < 60s → implicit_retry=1.
"""

from __future__ import annotations

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns a value in [-1, 1] where 1 means identical direction.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def is_reformulation(
    current: list[float],
    previous: list[float],
    time_delta_seconds: float,
    *,
    similarity_threshold: float = 0.7,
    max_time_seconds: float = 60.0,
) -> bool:
    """Detect if current query is a reformulation of previous query.

    Args:
        current: Dense embedding vector of the current query.
        previous: Dense embedding vector of the previous query.
        time_delta_seconds: Seconds elapsed since the previous query.
        similarity_threshold: Minimum cosine similarity to consider a reformulation.
        max_time_seconds: Maximum time window (exclusive) for reformulation detection.

    Returns:
        True if the query appears to be a reformulation (similarity > threshold
        AND time_delta < max_time_seconds), False otherwise.
    """
    if time_delta_seconds >= max_time_seconds:
        return False
    sim = cosine_similarity(current, previous)
    return sim > similarity_threshold
