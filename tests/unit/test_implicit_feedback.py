"""Tests for implicit retry detection via embedding similarity (#756)."""

import math


def _make_vec(dim: int = 4, value: float = 1.0) -> list[float]:
    """Create a unit vector in the given dimension."""
    raw = [value] * dim
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _similar_vec(base: list[float], noise: float = 0.05) -> list[float]:
    """Create a slightly perturbed version of base (still similar)."""
    noised = [x + noise * (i % 2 - 0.5) for i, x in enumerate(base)]
    norm = math.sqrt(sum(x * x for x in noised))
    return [x / norm for x in noised]


class TestIsReformulation:
    """Test the is_reformulation() function from implicit_feedback module."""

    def test_similar_query_within_60s_returns_true(self):
        """Similar query within 60s → implicit_retry=1 (reformulation detected)."""
        from telegram_bot.implicit_feedback import is_reformulation

        current = _make_vec()
        previous = _similar_vec(_make_vec())
        result = is_reformulation(current, previous, time_delta_seconds=30.0)
        assert result is True

    def test_different_query_returns_false(self):
        """Different query (low cosine similarity) → no implicit retry signal."""
        from telegram_bot.implicit_feedback import is_reformulation

        current = _make_vec(4, 1.0)
        # A nearly orthogonal vector will have similarity ~0
        previous = [1.0, 0.0, 0.0, 0.0]
        # current is [0.5, 0.5, 0.5, 0.5], previous is [1, 0, 0, 0]
        # cosine = 0.5, which is < 0.7 threshold
        result = is_reformulation(current, previous, time_delta_seconds=30.0)
        assert result is False

    def test_similar_query_after_60s_returns_false(self):
        """> 60s elapsed → no score even if queries are similar."""
        from telegram_bot.implicit_feedback import is_reformulation

        current = _make_vec()
        previous = _similar_vec(_make_vec())
        result = is_reformulation(current, previous, time_delta_seconds=61.0)
        assert result is False

    def test_exactly_60s_returns_false(self):
        """Exactly 60s is NOT within the window (strict less-than)."""
        from telegram_bot.implicit_feedback import is_reformulation

        current = _make_vec()
        previous = _similar_vec(_make_vec())
        result = is_reformulation(current, previous, time_delta_seconds=60.0)
        assert result is False

    def test_near_identical_query_returns_true(self):
        """Near-identical vectors (same query) should be detected as reformulation."""
        from telegram_bot.implicit_feedback import is_reformulation

        vec = _make_vec()
        result = is_reformulation(vec, vec, time_delta_seconds=5.0)
        assert result is True

    def test_similarity_threshold_boundary_below_returns_false(self):
        """Similarity just below 0.7 → not a reformulation."""
        import math

        from telegram_bot.implicit_feedback import is_reformulation

        # Create two vectors with cosine similarity ~0.65 (below threshold)
        # vec_a = [1, 0], vec_b = [cos(49.5°), sin(49.5°)]
        angle = math.radians(49.5)  # cosine ~0.648
        current = [1.0, 0.0]
        previous = [math.cos(angle), math.sin(angle)]
        result = is_reformulation(current, previous, time_delta_seconds=30.0)
        assert result is False

    def test_similarity_threshold_boundary_above_returns_true(self):
        """Similarity just above 0.7 → is a reformulation."""
        import math

        from telegram_bot.implicit_feedback import is_reformulation

        angle = math.radians(44.0)  # cosine ~0.719 (above 0.7)
        current = [1.0, 0.0]
        previous = [math.cos(angle), math.sin(angle)]
        result = is_reformulation(current, previous, time_delta_seconds=30.0)
        assert result is True

    def test_zero_time_delta_returns_true_for_similar(self):
        """Zero time delta (instant follow-up) with similar query → reformulation."""
        from telegram_bot.implicit_feedback import is_reformulation

        current = _make_vec()
        previous = _make_vec()
        result = is_reformulation(current, previous, time_delta_seconds=0.0)
        assert result is True

    def test_negative_time_delta_future_timestamp_returns_false(self):
        """Negative time_delta arises when prev_ts is in the future (clock skew / race condition).

        Edge case: time.time() - prev["ts"] < 0 when the stored timestamp is ahead of
        the current clock.  This should NOT trigger an implicit retry signal.
        Similar vectors are used to isolate the time_delta guard behaviour.
        """
        from telegram_bot.implicit_feedback import is_reformulation

        # Near-identical vectors → would be a reformulation if time window were valid
        current = _make_vec()
        previous = _make_vec()
        # Negative delta: previous query was timestamped 5s in the future
        result = is_reformulation(current, previous, time_delta_seconds=-5.0)
        # A future timestamp is outside the valid [0, max_time_seconds) window → False
        assert result is False


class TestCosineSimilarity:
    """Test the cosine_similarity helper."""

    def test_identical_vectors_have_similarity_one(self):
        """Identical vectors → cosine similarity = 1.0."""
        from telegram_bot.implicit_feedback import cosine_similarity

        v = [0.5, 0.5, 0.5, 0.5]
        sim = cosine_similarity(v, v)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors_have_similarity_zero(self):
        """Orthogonal vectors → cosine similarity = 0.0."""
        from telegram_bot.implicit_feedback import cosine_similarity

        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = cosine_similarity(a, b)
        assert abs(sim - 0.0) < 1e-6

    def test_opposite_vectors_have_similarity_negative_one(self):
        """Opposite vectors → cosine similarity = -1.0."""
        from telegram_bot.implicit_feedback import cosine_similarity

        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        sim = cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6
