"""Tests for RAGState schema and initial state factory."""

from __future__ import annotations


class TestRAGState:
    def test_has_required_fields(self):
        from telegram_bot.graph.state import RAGState

        annotations = RAGState.__annotations__
        required = [
            "messages",
            "user_id",
            "session_id",
            "query_type",
            "cache_hit",
            "cached_response",
            "query_embedding",
            "sparse_embedding",
            "documents",
            "documents_relevant",
            "rewrite_count",
            "rewrite_effective",
            "max_rewrite_attempts",
            "response",
            "latency_stages",
            "search_results_count",
            "rerank_applied",
            "grade_confidence",
        ]
        for field in required:
            assert field in annotations, f"Missing field: {field}"

    def test_initial_state_factory(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=123, session_id="s-abc", query="test")
        assert state["user_id"] == 123
        assert state["session_id"] == "s-abc"
        assert state["cache_hit"] is False
        assert state["rewrite_count"] == 0
        assert len(state["messages"]) == 1
        assert state["documents"] == []
        assert state["documents_relevant"] is False
        assert state["response"] == ""
        assert state["latency_stages"] == {}
        assert state["search_results_count"] == 0
        assert state["rerank_applied"] is False
        assert state["query_embedding"] is None
        assert state["sparse_embedding"] is None
        assert state["cached_response"] is None
        assert state["query_type"] == ""

    def test_messages_contains_user_query(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s-1", query="Привет!")
        msg = state["messages"][0]
        assert msg["role"] == "user"
        assert msg["content"] == "Привет!"

    def test_initial_state_has_max_rewrite_attempts(self):
        """Initial state includes max_rewrite_attempts=1."""
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="test")
        assert state["max_rewrite_attempts"] == 1

    def test_initial_state_has_rewrite_effective(self):
        """Initial state includes rewrite_effective=True."""
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="test")
        assert state["rewrite_effective"] is True

    def test_initial_state_has_grade_confidence(self):
        """Initial state includes grade_confidence=0.0."""
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="test")
        assert state["grade_confidence"] == 0.0

    def test_has_trace_id(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=123, session_id="s-test", query="hello")
        assert "trace_id" in state
        assert state["trace_id"] == ""

    def test_has_sent_message(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=123, session_id="s-test", query="hello")
        assert "sent_message" in state
        assert state["sent_message"] is None

    def test_has_injection_fields(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=123, session_id="s-test", query="hello")
        assert state["injection_detected"] is False
        assert state["injection_risk_score"] == 0.0
        assert state["injection_pattern"] is None

    def test_rag_state_has_injection_annotations(self):
        from telegram_bot.graph.state import RAGState

        annotations = RAGState.__annotations__
        assert "injection_detected" in annotations
        assert "injection_risk_score" in annotations
        assert "injection_pattern" in annotations
