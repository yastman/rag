"""Tests for conditional edge routing functions."""

from __future__ import annotations

import pytest

from telegram_bot.graph.edges import route_by_query_type, route_cache, route_grade, route_start
from telegram_bot.graph.state import make_initial_state


class TestRouteStart:
    def test_voice_audio_present_routes_to_transcribe(self):
        state = make_initial_state(user_id=1, session_id="s", query="")
        state["voice_audio"] = b"fake-ogg"
        assert route_start(state) == "transcribe"

    def test_voice_audio_none_routes_to_classify(self):
        state = make_initial_state(user_id=1, session_id="s", query="hello")
        state["voice_audio"] = None
        assert route_start(state) == "classify"

    def test_voice_audio_absent_routes_to_classify(self):
        state = {"query": "hello"}  # no voice_audio key at all
        assert route_start(state) == "classify"


def test_initial_state_has_score_improved():
    """make_initial_state должен включать score_improved=True."""
    state = make_initial_state(user_id=1, session_id="s", query="test")
    assert state["score_improved"] is True


class TestRouteByQueryType:
    @pytest.mark.parametrize(
        ("query_type", "expected"),
        [
            pytest.param("CHITCHAT", "respond", id="chitchat"),
            pytest.param("OFF_TOPIC", "respond", id="off_topic"),
            pytest.param("STRUCTURED", "cache_check", id="structured"),
            pytest.param("FAQ", "cache_check", id="faq"),
            pytest.param("ENTITY", "cache_check", id="entity"),
            pytest.param("GENERAL", "cache_check", id="general"),
        ],
    )
    def test_routes_by_query_type(self, query_type, expected):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["query_type"] = query_type
        assert route_by_query_type(state) == expected


class TestRouteCache:
    def test_cache_hit_routes_to_respond(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["cache_hit"] = True
        assert route_cache(state) == "respond"

    def test_cache_miss_routes_to_retrieve(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["cache_hit"] = False
        assert route_cache(state) == "retrieve"

    def test_embedding_error_routes_to_respond(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["embedding_error"] = True
        state["cache_hit"] = False
        assert route_cache(state) == "respond"


class TestRouteGrade:
    def test_relevant_routes_to_rerank(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = True
        state["rewrite_count"] = 0
        assert route_grade(state) == "rerank"

    def test_skip_rerank_routes_to_generate(self):
        state = {
            "documents_relevant": True,
            "rewrite_count": 0,
            "rewrite_effective": True,
            "grade_confidence": 0.95,
            "skip_rerank": True,
        }
        assert route_grade(state) == "generate"

    def test_no_skip_rerank_routes_to_rerank(self):
        state = {
            "documents_relevant": True,
            "rewrite_count": 0,
            "rewrite_effective": True,
            "grade_confidence": 0.5,
            "skip_rerank": False,
        }
        assert route_grade(state) == "rerank"

    def test_not_relevant_first_attempt_routes_to_rewrite(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 0
        assert route_grade(state) == "rewrite"

    def test_not_relevant_max_rewrite_attempts_routes_to_generate(self):
        """max_rewrite_attempts=1 (default), rewrite_count=1 → generate."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 1,
            "rewrite_effective": True,
            "max_rewrite_attempts": 1,
        }
        assert route_grade(state) == "generate"

    def test_max_rewrite_attempts_from_state(self):
        """With max_rewrite_attempts=3, rewrite_count=2 still rewrites."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 2,
            "rewrite_effective": True,
            "max_rewrite_attempts": 3,
        }
        assert route_grade(state) == "rewrite"

    def test_not_relevant_exceeded_retries_routes_to_generate(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 5
        assert route_grade(state) == "generate"

    def test_custom_max_rewrite_attempts(self):
        """With max_rewrite_attempts=3, rewrite_count=2 still allows rewrite."""
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 2
        state["max_rewrite_attempts"] = 3
        assert route_grade(state) == "rewrite"

    def test_custom_max_rewrite_attempts_exhausted(self):
        """With max_rewrite_attempts=3, rewrite_count=3 → generate."""
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 3
        state["max_rewrite_attempts"] = 3
        assert route_grade(state) == "generate"

    def test_route_grade_rewrite_ineffective_goes_to_generate(self):
        """If rewrite was ineffective, skip further rewrites."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 1,
            "rewrite_effective": False,
        }
        assert route_grade(state) == "generate"

    def test_route_grade_rewrite_effective_allows_retry(self):
        """If rewrite was effective but docs still not relevant, allow another rewrite."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 1,
            "rewrite_effective": True,
        }
        assert route_grade(state) == "rewrite"

    def test_score_not_improved_stops_rewrite(self):
        """If score didn't improve, stop rewriting even if count < max."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 1,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": False,
        }
        assert route_grade(state) == "generate"

    def test_score_improved_allows_rewrite(self):
        """If score improved and conditions met, allow rewrite."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 1,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": True,
        }
        assert route_grade(state) == "rewrite"

    def test_score_improved_default_true_allows_rewrite(self):
        """Missing score_improved defaults to True (backward compat)."""
        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 1,
            "rewrite_effective": True,
        }
        assert route_grade(state) == "rewrite"
