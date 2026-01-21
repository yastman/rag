"""Tests for CESCPersonalizer."""

import pytest

from telegram_bot.services.cesc import CESCPersonalizer


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
