"""Tests for classify_node — 6-type query taxonomy."""

from __future__ import annotations

import pytest

from telegram_bot.graph.nodes.classify import (
    CHITCHAT,
    ENTITY,
    FAQ,
    GENERAL,
    OFF_TOPIC,
    STRUCTURED,
    classify_node,
    classify_query,
)
from telegram_bot.graph.state import make_initial_state


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

    async def test_chitchat_returns_response(self):
        state = make_initial_state(user_id=1, session_id="s", query="Привет!")
        result = await classify_node(state)
        assert result["query_type"] == CHITCHAT
        assert result["response"]  # non-empty canned response
        assert "classify" in result["latency_stages"]

    async def test_off_topic_returns_response(self):
        state = make_initial_state(user_id=1, session_id="s", query="как написать код на python")
        result = await classify_node(state)
        assert result["query_type"] == OFF_TOPIC
        assert result["response"]

    async def test_structured_no_canned_response(self):
        state = make_initial_state(user_id=1, session_id="s", query="2 комнаты до 80000 евро")
        result = await classify_node(state)
        assert result["query_type"] == STRUCTURED
        assert "response" not in result

    async def test_faq_no_canned_response(self):
        state = make_initial_state(user_id=1, session_id="s", query="как оформить покупку")
        result = await classify_node(state)
        assert result["query_type"] == FAQ
        assert "response" not in result

    async def test_records_latency(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        result = await classify_node(state)
        assert isinstance(result["latency_stages"]["classify"], float)
        assert result["latency_stages"]["classify"] >= 0

    async def test_preserves_existing_latency_stages(self):
        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["latency_stages"] = {"prev": 0.5}
        result = await classify_node(state)
        assert result["latency_stages"]["prev"] == 0.5
        assert "classify" in result["latency_stages"]
