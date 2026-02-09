"""Tests for conditional edge routing functions."""

from __future__ import annotations

from telegram_bot.graph.edges import route_by_query_type, route_cache, route_grade
from telegram_bot.graph.state import make_initial_state


class TestRouteByQueryType:
    def test_chitchat_routes_to_respond(self):
        state = make_initial_state(user_id=1, session_id="s", query="hi")
        state["query_type"] = "CHITCHAT"
        assert route_by_query_type(state) == "respond"

    def test_off_topic_routes_to_respond(self):
        state = make_initial_state(user_id=1, session_id="s", query="python code")
        state["query_type"] = "OFF_TOPIC"
        assert route_by_query_type(state) == "respond"

    def test_structured_routes_to_cache_check(self):
        state = make_initial_state(user_id=1, session_id="s", query="2 rooms 80k")
        state["query_type"] = "STRUCTURED"
        assert route_by_query_type(state) == "cache_check"

    def test_faq_routes_to_cache_check(self):
        state = make_initial_state(user_id=1, session_id="s", query="how to buy")
        state["query_type"] = "FAQ"
        assert route_by_query_type(state) == "cache_check"

    def test_entity_routes_to_cache_check(self):
        state = make_initial_state(user_id=1, session_id="s", query="Nesebar")
        state["query_type"] = "ENTITY"
        assert route_by_query_type(state) == "cache_check"

    def test_general_routes_to_cache_check(self):
        state = make_initial_state(user_id=1, session_id="s", query="cozy apartment")
        state["query_type"] = "GENERAL"
        assert route_by_query_type(state) == "cache_check"


class TestRouteCache:
    def test_cache_hit_routes_to_respond(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["cache_hit"] = True
        assert route_cache(state) == "respond"

    def test_cache_miss_routes_to_retrieve(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["cache_hit"] = False
        assert route_cache(state) == "retrieve"


class TestRouteGrade:
    def test_relevant_routes_to_rerank(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = True
        state["rewrite_count"] = 0
        assert route_grade(state) == "rerank"

    def test_not_relevant_first_attempt_routes_to_rewrite(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 0
        assert route_grade(state) == "rewrite"

    def test_not_relevant_second_attempt_routes_to_rewrite(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 1
        assert route_grade(state) == "rewrite"

    def test_not_relevant_max_retries_routes_to_generate(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 2
        assert route_grade(state) == "generate"

    def test_not_relevant_exceeded_retries_routes_to_generate(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents_relevant"] = False
        state["rewrite_count"] = 5
        assert route_grade(state) == "generate"
