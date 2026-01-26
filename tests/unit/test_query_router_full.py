"""Comprehensive tests for query_router module."""

import pytest

from telegram_bot.services.query_router import (
    QueryType,
    classify_query,
    get_chitchat_response,
    needs_rerank,
)


class TestClassifyQueryChitchat:
    """Tests for CHITCHAT classification."""

    @pytest.mark.parametrize(
        "query",
        [
            "Привет",
            "привет!",
            "ПРИВЕТ",
            "Здравствуйте",
            "здравствуй",
            "Добрый день",
            "добрый день!",
            "Доброе утро",
            "Добрый вечер",
            "Хай",
            "хай!",
            "Хелло",
            "Салют",
        ],
    )
    def test_classify_greetings_russian(self, query):
        """Test Russian greetings classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize(
        "query",
        [
            "Hi",
            "hi!",
            "Hello",
            "hello there",
            "Hey",
            "hey!",
            "Good morning",
            "Good afternoon",
            "Good evening",
        ],
    )
    def test_classify_greetings_english(self, query):
        """Test English greetings classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize(
        "query",
        [
            "Спасибо",
            "спасибо!",
            "Благодарю",
            "благодарю вас",
            "Круто",
            "круто!",
            "Отлично",
            "Супер",
            "супер!",
        ],
    )
    def test_classify_thanks_russian(self, query):
        """Test Russian thanks classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize(
        "query",
        [
            "Thanks",
            "thanks!",
            "Thank you",
            "thank you so much",
            "Great",
            "great!",
            "Awesome",
        ],
    )
    def test_classify_thanks_english(self, query):
        """Test English thanks classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize(
        "query",
        [
            "Что ты умеешь",
            "что ты можешь",
            "Как тебя зовут",
            "Кто ты",
            "Ты бот",
            "ты бот?",
        ],
    )
    def test_classify_bot_questions_russian(self, query):
        """Test Russian bot questions classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize(
        "query",
        [
            "What can you do",
            "what do you do",
            "Who are you",
            "Are you a bot",
            "are you ai",
        ],
    )
    def test_classify_bot_questions_english(self, query):
        """Test English bot questions classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize(
        "query",
        [
            "Пока",
            "пока!",
            "До свидания",
            "Всего доброго",
            "Bye",
            "bye!",
            "Goodbye",
            "See you",
        ],
    )
    def test_classify_farewells(self, query):
        """Test farewells classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT


class TestClassifyQuerySimple:
    """Tests for SIMPLE classification."""

    @pytest.mark.parametrize(
        "query",
        [
            "Сколько стоит",
            "сколько стоит квартира",
            "Какая цена",
            "Price",
            "price of this",
        ],
    )
    def test_classify_price_questions(self, query):
        """Test price questions classified as SIMPLE."""
        assert classify_query(query) == QueryType.SIMPLE

    @pytest.mark.parametrize(
        "query",
        [
            "2 комнаты",
            "3 спальни",
            "однокомнатная",
            "двухкомнатная",
            "трёхкомнатная",
        ],
    )
    def test_classify_room_queries(self, query):
        """Test room count queries classified as SIMPLE."""
        assert classify_query(query) == QueryType.SIMPLE


class TestClassifyQueryComplex:
    """Tests for COMPLEX classification."""

    @pytest.mark.parametrize(
        "query",
        [
            # Note: "двухкомнатная квартира в Бургасе..." matches SIMPLE pattern
            "сравни цены в Несебре и Солнечном берегу",
            "найди недвижимость с видом на море",
            "квартиры в новостройках",
            "дома с бассейном",
            "апартаменты на первой линии",
            "инвестиционная недвижимость в Болгарии",
        ],
    )
    def test_classify_complex_queries(self, query):
        """Test complex queries classified as COMPLEX."""
        assert classify_query(query) == QueryType.COMPLEX

    def test_classify_room_in_complex_query_as_simple(self):
        """Test that queries starting with room patterns are SIMPLE."""
        # This is expected behavior - pattern matching is prefix-based
        result = classify_query("двухкомнатная квартира в Бургасе до 100000 евро у моря")
        assert result == QueryType.SIMPLE

    def test_classify_unknown_query(self):
        """Test unknown queries default to COMPLEX."""
        assert classify_query("random search query") == QueryType.COMPLEX

    def test_classify_empty_query(self):
        """Test empty query classified as COMPLEX."""
        assert classify_query("") == QueryType.COMPLEX

    def test_classify_whitespace_query(self):
        """Test whitespace-only query classified as COMPLEX."""
        assert classify_query("   ") == QueryType.COMPLEX


class TestGetChitchatResponse:
    """Tests for get_chitchat_response function."""

    def test_greeting_response_russian(self):
        """Test response to Russian greeting."""
        response = get_chitchat_response("Привет")

        assert response is not None
        assert len(response) > 0
        # Should be one of the greeting responses
        assert any(word in response.lower() for word in ["привет", "здравствуйте", "помогу"])

    def test_greeting_response_english(self):
        """Test response to English greeting."""
        response = get_chitchat_response("Hello")

        assert response is not None

    def test_thanks_response(self):
        """Test response to thanks."""
        response = get_chitchat_response("Спасибо")

        assert response is not None
        assert any(word in response.lower() for word in ["пожалуйста", "рад"])

    def test_bot_info_response(self):
        """Test response to bot info question."""
        response = get_chitchat_response("Кто ты")

        assert response is not None
        assert "бот" in response.lower() or "недвижимост" in response.lower()

    def test_farewell_response(self):
        """Test response to farewell."""
        response = get_chitchat_response("Пока")

        assert response is not None
        assert any(word in response.lower() for word in ["свидания", "удачи", "доброго"])

    def test_non_chitchat_returns_none(self):
        """Test non-chitchat query returns None."""
        response = get_chitchat_response("квартиры в Бургасе")

        assert response is None

    def test_complex_query_returns_none(self):
        """Test complex query returns None."""
        response = get_chitchat_response("двухкомнатная квартира у моря до 50000")

        assert response is None


class TestNeedsRerank:
    """Tests for needs_rerank function."""

    def test_chitchat_with_few_results_no_rerank(self):
        """Test CHITCHAT with few results doesn't need rerank."""
        # CHITCHAT is not explicitly handled by needs_rerank (skipped before reaching it)
        # But if called, it behaves like COMPLEX (only checks SIMPLE and result count)
        assert needs_rerank(QueryType.CHITCHAT, result_count=0) is False
        assert needs_rerank(QueryType.CHITCHAT, result_count=2) is False

    def test_chitchat_with_many_results_needs_rerank(self):
        """Test CHITCHAT with many results technically needs rerank (edge case).

        Note: In practice, CHITCHAT queries are handled before needs_rerank is called.
        But if needs_rerank is called with CHITCHAT, it doesn't have special handling.
        """
        # This is a documentation test - CHITCHAT should be handled at routing level
        assert needs_rerank(QueryType.CHITCHAT, result_count=5) is True

    def test_simple_never_needs_rerank(self):
        """Test SIMPLE never needs rerank."""
        assert needs_rerank(QueryType.SIMPLE, result_count=0) is False
        assert needs_rerank(QueryType.SIMPLE, result_count=5) is False
        assert needs_rerank(QueryType.SIMPLE, result_count=100) is False

    def test_complex_needs_rerank_with_enough_results(self):
        """Test COMPLEX needs rerank with > 2 results."""
        assert needs_rerank(QueryType.COMPLEX, result_count=3) is True
        assert needs_rerank(QueryType.COMPLEX, result_count=5) is True
        assert needs_rerank(QueryType.COMPLEX, result_count=10) is True

    def test_complex_no_rerank_with_few_results(self):
        """Test COMPLEX doesn't need rerank with <= 2 results."""
        assert needs_rerank(QueryType.COMPLEX, result_count=0) is False
        assert needs_rerank(QueryType.COMPLEX, result_count=1) is False
        assert needs_rerank(QueryType.COMPLEX, result_count=2) is False

    def test_rerank_boundary_case(self):
        """Test rerank at boundary (2 vs 3 results)."""
        assert needs_rerank(QueryType.COMPLEX, result_count=2) is False
        assert needs_rerank(QueryType.COMPLEX, result_count=3) is True


class TestQueryTypeEnum:
    """Tests for QueryType enum."""

    def test_enum_values(self):
        """Test QueryType enum has expected values."""
        assert QueryType.CHITCHAT.value == "chitchat"
        assert QueryType.SIMPLE.value == "simple"
        assert QueryType.COMPLEX.value == "complex"

    def test_enum_members(self):
        """Test QueryType enum has all expected members."""
        members = [m.name for m in QueryType]
        assert "CHITCHAT" in members
        assert "SIMPLE" in members
        assert "COMPLEX" in members
        assert len(members) == 3
