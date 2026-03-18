"""Tests for classify_node — 6-type query taxonomy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langgraph.runtime import Runtime

from telegram_bot.graph.nodes.classify import (
    CHITCHAT,
    CHITCHAT_RESPONSES,
    ENTITY,
    FAQ,
    GENERAL,
    OFF_TOPIC,
    OFF_TOPIC_RESPONSES,
    STRUCTURED,
    _get_chitchat_response,
    classify_node,
    classify_query,
)
from telegram_bot.graph.state import make_initial_state


def _make_runtime(**ctx) -> Runtime:
    """Create a Runtime with GraphContext for node tests."""
    return Runtime(context=ctx)


class TestClassifyQuery:
    """Unit tests for the pure classify_query function."""

    @pytest.mark.parametrize(
        "query",
        ["Привет!", "hello", "Добрый день", "спасибо", "пока", "кто ты", "bye"],
    )
    def test_chitchat(self, query: str):
        assert classify_query(query) == CHITCHAT

    @pytest.mark.parametrize(
        "query",
        ["как написать код на python", "рецепт борща", "формула воды", "фильм на вечер"],
    )
    def test_off_topic(self, query: str):
        assert classify_query(query) == OFF_TOPIC

    @pytest.mark.parametrize(
        "query",
        ["2 комнаты до 80000 евро", "трёхкомнатная квартира", "до 50000€", "этаж 3"],
    )
    def test_structured(self, query: str):
        assert classify_query(query) == STRUCTURED

    @pytest.mark.parametrize(
        "query",
        ["как оформить покупку", "какие документы нужны", "сколько стоит оформление"],
    )
    def test_faq(self, query: str):
        assert classify_query(query) == FAQ

    @pytest.mark.parametrize(
        "query",
        ["квартира в Несебре", "Солнечный берег апартаменты", "Sunny Beach villa"],
    )
    def test_entity(self, query: str):
        assert classify_query(query) == ENTITY

    def test_general(self):
        assert classify_query("уютная квартира с видом на море") == GENERAL


class TestClassifyNode:
    """Integration tests for the classify_node LangGraph node."""

    @pytest.mark.parametrize(
        ("query", "expected_type"),
        [
            ("Привет!", CHITCHAT),
            ("как написать код на python", OFF_TOPIC),
        ],
    )
    async def test_early_exit_returns_canned_response(self, query, expected_type):
        """CHITCHAT and OFF_TOPIC queries produce a canned response (early exit)."""
        state = make_initial_state(user_id=1, session_id="s", query=query)
        result = await classify_node(state, _make_runtime())
        assert result["query_type"] == expected_type
        assert result["response"]  # non-empty canned response
        assert "classify" in result["latency_stages"]

    @pytest.mark.parametrize(
        ("query", "expected_type"),
        [
            ("2 комнаты до 80000 евро", STRUCTURED),
            ("как оформить покупку", FAQ),
        ],
    )
    async def test_rag_types_have_no_canned_response(self, query, expected_type):
        """STRUCTURED and FAQ queries continue to RAG pipeline (no canned response)."""
        state = make_initial_state(user_id=1, session_id="s", query=query)
        result = await classify_node(state, _make_runtime())
        assert result["query_type"] == expected_type
        assert "response" not in result

    async def test_records_latency(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        result = await classify_node(state, _make_runtime())
        assert isinstance(result["latency_stages"]["classify"], float)
        assert result["latency_stages"]["classify"] >= 0

    async def test_preserves_existing_latency_stages(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["latency_stages"] = {"prev": 0.5}
        result = await classify_node(state, _make_runtime())
        assert result["latency_stages"]["prev"] == 0.5
        assert "classify" in result["latency_stages"]

    def test_chitchat_response_uses_secrets_choice(self):
        with patch("telegram_bot.graph.nodes.classify.choice", return_value="secure hi") as mocked:
            response = _get_chitchat_response("Привет!")

        assert response == "secure hi"
        mocked.assert_called_once_with(CHITCHAT_RESPONSES["greeting"])

    async def test_off_topic_response_uses_secrets_choice(self):
        state = make_initial_state(user_id=1, session_id="s", query="как написать код на python")

        with patch(
            "telegram_bot.graph.nodes.classify.choice", return_value="secure off-topic"
        ) as mocked:
            result = await classify_node(state, _make_runtime())

        assert result["query_type"] == OFF_TOPIC
        assert result["response"] == "secure off-topic"
        mocked.assert_called_once_with(OFF_TOPIC_RESPONSES)


class TestClassifyNodeSemanticMode:
    """Tests for classify_node with SemanticClassifier injected via Runtime."""

    def _make_classifier(self, query_type: str, available: bool = True) -> MagicMock:
        classifier = MagicMock()
        classifier.available = available
        classifier.classify.return_value = query_type
        return classifier

    async def test_semantic_mode_uses_classifier(self):
        classifier = self._make_classifier(FAQ)
        state = make_initial_state(user_id=1, session_id="s", query="как оформить покупку")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        assert result["query_type"] == FAQ
        classifier.classify.assert_called_once_with("как оформить покупку")

    async def test_semantic_mode_chitchat_returns_canned_response(self):
        classifier = self._make_classifier(CHITCHAT)
        state = make_initial_state(user_id=1, session_id="s", query="привет")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        assert result["query_type"] == CHITCHAT
        assert result["response"]

    async def test_semantic_mode_off_topic_returns_canned_response(self):
        classifier = self._make_classifier(OFF_TOPIC)
        state = make_initial_state(user_id=1, session_id="s", query="рецепт борща")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        assert result["query_type"] == OFF_TOPIC
        assert result["response"]

    async def test_semantic_mode_structured_no_canned_response(self):
        classifier = self._make_classifier(STRUCTURED)
        state = make_initial_state(user_id=1, session_id="s", query="2 комнаты до 80000 евро")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        assert result["query_type"] == STRUCTURED
        assert "response" not in result

    async def test_semantic_mode_general_no_canned_response(self):
        classifier = self._make_classifier(GENERAL)
        state = make_initial_state(user_id=1, session_id="s", query="квартира у моря")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        assert result["query_type"] == GENERAL
        assert "response" not in result

    async def test_fallback_to_regex_when_classifier_unavailable(self):
        classifier = self._make_classifier(FAQ, available=False)
        state = make_initial_state(user_id=1, session_id="s", query="Привет!")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        # unavailable → regex → CHITCHAT
        assert result["query_type"] == CHITCHAT
        classifier.classify.assert_not_called()

    async def test_fallback_to_regex_on_classifier_exception(self):
        classifier = MagicMock()
        classifier.available = True
        classifier.classify.side_effect = RuntimeError("Redis gone")
        state = make_initial_state(user_id=1, session_id="s", query="Привет!")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        # fallback → regex → CHITCHAT
        assert result["query_type"] == CHITCHAT

    async def test_no_classifier_uses_regex(self):
        state = make_initial_state(user_id=1, session_id="s", query="Привет!")
        result = await classify_node(state, _make_runtime())
        assert result["query_type"] == CHITCHAT

    async def test_semantic_mode_records_latency(self):
        classifier = self._make_classifier(FAQ)
        state = make_initial_state(user_id=1, session_id="s", query="как оформить покупку")
        result = await classify_node(state, _make_runtime(classifier=classifier))
        assert isinstance(result["latency_stages"]["classify"], float)
        assert result["latency_stages"]["classify"] >= 0

    async def test_semantic_classifier_called_via_asyncio_to_thread(self):
        """classifier.classify must be called via asyncio.to_thread (non-blocking)."""
        import asyncio
        from unittest.mock import patch

        classifier = self._make_classifier(FAQ)
        state = make_initial_state(user_id=1, session_id="s", query="как оформить покупку")

        thread_calls: list[tuple[object, ...]] = []

        original_to_thread = asyncio.to_thread

        async def recording_to_thread(func, *args, **kwargs):
            thread_calls.append((func, args, kwargs))
            return await original_to_thread(func, *args, **kwargs)

        with patch("telegram_bot.graph.nodes.classify.asyncio.to_thread", new=recording_to_thread):
            result = await classify_node(state, _make_runtime(classifier=classifier))

        # asyncio.to_thread must have been called with classifier.classify and the query
        assert len(thread_calls) == 1
        called_func, called_args, _ = thread_calls[0]
        assert called_func is classifier.classify
        assert called_args == ("как оформить покупку",)
        assert result["query_type"] == FAQ
