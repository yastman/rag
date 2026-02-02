"""Tests for CESCPersonalizer and is_personalized_query."""

import pytest

from telegram_bot.services.cesc import CESCPersonalizer, is_personalized_query


class TestIsPersonalizedQuery:
    """Tests for is_personalized_query function."""

    # Test personal markers (Russian)
    @pytest.mark.parametrize(
        "query",
        [
            "покажи мне квартиры",
            "мне подойдёт",
            "Я предпочитаю большие комнаты",
            "как в прошлый раз",
            "для моего бюджета",
            "мой бюджет 50000",
            "моя квартира",
            "мои предпочтения",
            "по моим критериям",
            "исходя из моих требований",
            "учитывая мои пожелания",
            "под мои нужды",
        ],
    )
    def test_russian_personal_markers(self, query):
        """Test Russian personal markers trigger personalization."""
        assert is_personalized_query(query) is True

    # Test personal markers (English)
    @pytest.mark.parametrize(
        "query",
        [
            "find apartments for me",
            "I prefer large rooms",
            "my budget is 50000",
            "like last time please",
        ],
    )
    def test_english_personal_markers(self, query):
        """Test English personal markers trigger personalization."""
        assert is_personalized_query(query) is True

    # Test generic queries (no markers)
    @pytest.mark.parametrize(
        "query",
        [
            "квартиры в Бургасе",
            "двухкомнатная квартира",
            "недвижимость у моря",
            "цены на квартиры",
            "apartments in Burgas",
            "two bedroom flat",
        ],
    )
    def test_generic_queries_no_markers(self, query):
        """Test generic queries without markers don't trigger personalization."""
        assert is_personalized_query(query) is False

    def test_generic_query_with_user_preferences(self):
        """Test generic query triggers personalization when user has preferences."""
        context = {"preferences": {"cities": ["Бургас"]}}

        # Generic query but user has preferences
        assert is_personalized_query("квартиры", context) is True

    def test_generic_query_with_budget_preference(self):
        """Test generic query triggers personalization when user has budget."""
        context = {"preferences": {"budget_max": 100000}}

        assert is_personalized_query("квартиры", context) is True

    def test_generic_query_with_property_types(self):
        """Test generic query triggers personalization when user has property types."""
        context = {"preferences": {"property_types": ["apartment"]}}

        assert is_personalized_query("квартиры", context) is True

    def test_generic_query_empty_context(self):
        """Test generic query with empty context doesn't trigger personalization."""
        context = {"preferences": {}}

        assert is_personalized_query("квартиры", context) is False

    def test_generic_query_no_context(self):
        """Test generic query with None context doesn't trigger personalization."""
        assert is_personalized_query("квартиры", None) is False

    def test_marker_takes_priority_over_empty_context(self):
        """Test personal marker triggers even with empty context."""
        context = {"preferences": {}}

        # Has marker but no preferences - should still trigger
        assert is_personalized_query("покажи мне квартиры", context) is True

    def test_case_insensitive_markers(self):
        """Test markers are case insensitive."""
        assert is_personalized_query("МНЕ нужна квартира") is True
        assert is_personalized_query("MY budget is 50000") is True

    def test_marker_in_middle_of_query(self):
        """Test markers work when not at start of query."""
        assert is_personalized_query("найди квартиру для моего бюджета") is True

    def test_partial_marker_not_matched(self):
        """Test partial word match doesn't trigger (word boundaries)."""
        # "мне" shouldn't match in "именно"
        # Actually "мне" could match as a standalone word - let's use better example
        # "моя" shouldn't match in "немоям" (if such word existed)
        # Testing with actual word boundary behavior
        assert is_personalized_query("именно такой вариант") is False


class TestCESCPersonalizer:
    """Tests for CESC personalization logic."""

    def test_should_personalize_with_cities(self):
        """Test personalization enabled when cities present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"cities": ["Бургас"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_budget(self):
        """Test personalization enabled when budget present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"budget_max": 100000}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_property_types(self):
        """Test personalization enabled when property types present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"property_types": ["apartment"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_rooms(self):
        """Test personalization enabled when rooms present."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"rooms": 2}}

        assert personalizer.should_personalize(context) is True

    def test_should_not_personalize_empty_prefs(self):
        """Test personalization disabled when preferences empty."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {}}

        assert personalizer.should_personalize(context) is False

    def test_should_not_personalize_no_prefs_key(self):
        """Test personalization disabled when no preferences key."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {}

        assert personalizer.should_personalize(context) is False

    def test_build_prompt_with_full_context(self):
        """Test prompt building with full user context."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {
            "preferences": {
                "cities": ["Бургас", "Несебр"],
                "budget_max": 100000,
                "property_types": ["apartment", "studio"],
            },
            "profile_summary": "Ищет квартиры у моря",
        }
        cached_response = "Вот информация о недвижимости."

        prompt = personalizer._build_prompt(cached_response, context)

        assert "Бургас" in prompt
        assert "Несебр" in prompt
        assert "100000" in prompt
        assert "apartment" in prompt
        assert "Ищет квартиры у моря" in prompt
        assert "Вот информация о недвижимости" in prompt

    def test_build_prompt_with_missing_fields(self):
        """Test prompt building gracefully handles missing fields."""
        personalizer = CESCPersonalizer(llm_service=None)
        context = {"preferences": {"cities": ["Бургас"]}}
        cached_response = "Ответ"

        prompt = personalizer._build_prompt(cached_response, context)

        assert "Бургас" in prompt
        assert "не указан" in prompt  # Default for missing budget
        assert "новый пользователь" in prompt  # Default for missing summary


class TestCESCPersonalizerAsync:
    """Async tests for CESCPersonalizer."""

    @pytest.mark.asyncio
    async def test_personalize_returns_cached_when_no_prefs(self):
        """Test personalize returns cached response when no preferences."""
        personalizer = CESCPersonalizer(llm_service=None)
        cached_response = "Cached answer"
        context = {"preferences": {}}

        result = await personalizer.personalize(cached_response, context, "query")

        assert result == cached_response

    @pytest.mark.asyncio
    async def test_personalize_returns_cached_when_llm_fails(self):
        """Test personalize returns cached response when LLM fails."""

        class FailingLLM:
            async def generate(self, prompt, max_tokens):
                raise RuntimeError("LLM failed")

        personalizer = CESCPersonalizer(llm_service=FailingLLM())
        cached_response = "Cached answer"
        context = {"preferences": {"cities": ["Бургас"]}}

        result = await personalizer.personalize(cached_response, context, "query")

        assert result == cached_response

    @pytest.mark.asyncio
    async def test_personalize_calls_llm_with_prefs(self):
        """Test personalize calls LLM when preferences exist."""

        class MockLLM:
            def __init__(self):
                self.called_with = None

            async def generate(self, prompt, max_tokens):
                self.called_with = (prompt, max_tokens)
                return "Personalized response"

        mock_llm = MockLLM()
        personalizer = CESCPersonalizer(llm_service=mock_llm)
        cached_response = "Cached answer"
        context = {"preferences": {"cities": ["Бургас"]}}

        result = await personalizer.personalize(cached_response, context, "query")

        assert result == "Personalized response"
        assert mock_llm.called_with is not None
        assert "Бургас" in mock_llm.called_with[0]
        assert mock_llm.called_with[1] == 300
