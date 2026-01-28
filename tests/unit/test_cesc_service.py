"""Tests for CESC personalizer service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.cesc import (
    CESCPersonalizer,
    is_personalized_query,
)


class TestIsPersonalizedQuery:
    """Tests for is_personalized_query function."""

    def test_query_with_russian_marker_mne(self):
        """Test query with 'мне' marker returns True."""
        assert is_personalized_query("покажи мне квартиры") is True

    def test_query_with_russian_marker_ya_predpochitayu(self):
        """Test query with 'я предпочитаю' marker returns True."""
        assert is_personalized_query("я предпочитаю двухкомнатные") is True

    def test_query_with_russian_marker_moy_budget(self):
        """Test query with 'мой бюджет' marker returns True."""
        assert is_personalized_query("мой бюджет до 50000 евро") is True

    def test_query_with_english_marker_for_me(self):
        """Test query with 'for me' marker returns True."""
        assert is_personalized_query("find apartments for me") is True

    def test_query_with_english_marker_my_budget(self):
        """Test query with 'my budget' marker returns True."""
        assert is_personalized_query("my budget is 100k") is True

    def test_generic_query_no_markers(self):
        """Test generic query without markers returns False."""
        assert is_personalized_query("квартиры в Бургасе") is False

    def test_query_case_insensitive(self):
        """Test markers are matched case-insensitively."""
        assert is_personalized_query("МНЕ нужна квартира") is True
        assert is_personalized_query("For Me please") is True

    def test_query_with_user_context_preferences(self):
        """Test query with user preferences returns True."""
        context = {"preferences": {"cities": ["Бургас"]}}

        assert is_personalized_query("квартиры", context) is True

    def test_query_with_user_context_budget(self):
        """Test query with budget preference returns True."""
        context = {"preferences": {"budget_max": 50000}}

        assert is_personalized_query("квартиры", context) is True

    def test_query_with_empty_user_context(self):
        """Test query with empty context returns False."""
        context = {"preferences": {}}

        assert is_personalized_query("квартиры", context) is False

    def test_query_with_none_user_context(self):
        """Test query with None context returns False."""
        assert is_personalized_query("квартиры", None) is False


class TestCESCPersonalizerInit:
    """Tests for CESCPersonalizer initialization."""

    def test_init_stores_llm_service(self):
        """Test initializer stores LLM service."""
        mock_llm = MagicMock()

        personalizer = CESCPersonalizer(mock_llm)

        assert personalizer.llm is mock_llm


class TestShouldPersonalize:
    """Tests for CESCPersonalizer.should_personalize()."""

    @pytest.fixture
    def personalizer(self):
        return CESCPersonalizer(MagicMock())

    def test_should_personalize_with_cities(self, personalizer):
        """Test returns True when cities preference exists."""
        context = {"preferences": {"cities": ["Бургас"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_budget(self, personalizer):
        """Test returns True when budget_max preference exists."""
        context = {"preferences": {"budget_max": 100000}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_property_types(self, personalizer):
        """Test returns True when property_types preference exists."""
        context = {"preferences": {"property_types": ["apartment"]}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_with_rooms(self, personalizer):
        """Test returns True when rooms preference exists."""
        context = {"preferences": {"rooms": 2}}

        assert personalizer.should_personalize(context) is True

    def test_should_not_personalize_empty_prefs(self, personalizer):
        """Test returns False with empty preferences."""
        context = {"preferences": {}}

        assert personalizer.should_personalize(context) is False

    def test_should_not_personalize_no_prefs_key(self, personalizer):
        """Test returns False without preferences key."""
        context = {}

        assert personalizer.should_personalize(context) is False


class TestBuildPrompt:
    """Tests for CESCPersonalizer._build_prompt()."""

    @pytest.fixture
    def personalizer(self):
        return CESCPersonalizer(MagicMock())

    def test_build_prompt_includes_response(self, personalizer):
        """Test prompt includes cached response."""
        context = {"preferences": {}}

        prompt = personalizer._build_prompt("cached answer", context)

        assert "cached answer" in prompt

    def test_build_prompt_includes_cities(self, personalizer):
        """Test prompt includes cities from preferences."""
        context = {"preferences": {"cities": ["Бургас", "Варна"]}}

        prompt = personalizer._build_prompt("response", context)

        assert "Бургас" in prompt
        assert "Варна" in prompt

    def test_build_prompt_includes_budget(self, personalizer):
        """Test prompt includes budget from preferences."""
        context = {"preferences": {"budget_max": 50000}}

        prompt = personalizer._build_prompt("response", context)

        assert "50000" in prompt

    def test_build_prompt_truncates_long_response(self, personalizer):
        """Test prompt truncates response to 500 chars."""
        long_response = "x" * 1000
        context = {"preferences": {}}

        prompt = personalizer._build_prompt(long_response, context)

        # Should contain truncated response
        assert "x" * 500 in prompt
        assert "x" * 501 not in prompt

    def test_build_prompt_includes_profile_summary(self, personalizer):
        """Test prompt includes profile summary."""
        context = {
            "preferences": {},
            "profile_summary": "активный покупатель",
        }

        prompt = personalizer._build_prompt("response", context)

        assert "активный покупатель" in prompt

    def test_build_prompt_default_values(self, personalizer):
        """Test prompt uses defaults for missing values."""
        context = {"preferences": {}}

        prompt = personalizer._build_prompt("response", context)

        assert "любой" in prompt  # Default for cities
        assert "новый пользователь" in prompt  # Default profile


class TestPersonalize:
    """Tests for CESCPersonalizer.personalize()."""

    @pytest.fixture
    def personalizer(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="personalized response")
        return CESCPersonalizer(mock_llm)

    @pytest.mark.asyncio
    async def test_personalize_returns_personalized_response(self, personalizer):
        """Test personalize returns LLM response."""
        context = {"preferences": {"cities": ["Бургас"]}}

        result = await personalizer.personalize("cached response", context, "test query")

        assert result == "personalized response"
        personalizer.llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_personalize_skips_without_preferences(self, personalizer):
        """Test personalize returns cached when no preferences."""
        context = {"preferences": {}}

        result = await personalizer.personalize("cached response", context, "test query")

        assert result == "cached response"
        personalizer.llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_personalize_handles_llm_error(self, personalizer):
        """Test personalize returns cached on LLM error."""
        context = {"preferences": {"cities": ["Бургас"]}}
        personalizer.llm.generate.side_effect = Exception("LLM error")

        result = await personalizer.personalize("cached response", context, "test query")

        assert result == "cached response"

    @pytest.mark.asyncio
    async def test_personalize_strips_response(self, personalizer):
        """Test personalize strips whitespace from response."""
        context = {"preferences": {"cities": ["Бургас"]}}
        personalizer.llm.generate.return_value = "  response with spaces  "

        result = await personalizer.personalize("cached", context, "query")

        assert result == "response with spaces"

    @pytest.mark.asyncio
    async def test_personalize_with_no_prefs_key(self, personalizer):
        """Test personalize returns cached when preferences key missing."""
        context = {}

        result = await personalizer.personalize("cached response", context, "test query")

        assert result == "cached response"
        personalizer.llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_personalize_logs_user_id(self, personalizer):
        """Test personalize works with user_id in context."""
        context = {"preferences": {"cities": ["Бургас"]}, "user_id": "user123"}

        result = await personalizer.personalize("cached response", context, "test query")

        assert result == "personalized response"

    @pytest.mark.asyncio
    async def test_personalize_calls_llm_with_correct_params(self, personalizer):
        """Test personalize passes correct params to LLM."""
        context = {"preferences": {"cities": ["Бургас"]}}

        await personalizer.personalize("cached response", context, "test query")

        call_args = personalizer.llm.generate.call_args
        # Check that max_tokens=300 was passed
        assert call_args[1]["max_tokens"] == 300


class TestIsPersonalizedQueryExtended:
    """Additional tests for is_personalized_query edge cases."""

    def test_query_with_property_types_preference(self):
        """Test query with property_types preference returns True."""
        context = {"preferences": {"property_types": ["apartment"]}}

        assert is_personalized_query("недвижимость", context) is True

    def test_russian_marker_moya(self):
        """Test query with 'моя' marker returns True."""
        assert is_personalized_query("моя квартира") is True

    def test_russian_marker_moi(self):
        """Test query with 'мои' marker returns True."""
        assert is_personalized_query("мои предпочтения") is True

    def test_russian_marker_dlya_moego(self):
        """Test query with 'для моего' marker returns True."""
        assert is_personalized_query("для моего дома") is True

    def test_english_marker_i_prefer(self):
        """Test query with 'i prefer' marker returns True."""
        assert is_personalized_query("i prefer 2 bedrooms") is True

    def test_english_marker_like_last_time(self):
        """Test query with 'like last time' marker returns True."""
        assert is_personalized_query("show me apartments like last time") is True

    def test_russian_marker_po_moim(self):
        """Test query with 'по моим' marker returns True."""
        assert is_personalized_query("по моим критериям") is True

    def test_russian_marker_ishodya_iz_moih(self):
        """Test query with 'исходя из моих' marker returns True."""
        assert is_personalized_query("исходя из моих предпочтений") is True

    def test_russian_marker_uchityvaya_moi(self):
        """Test query with 'учитывая мои' marker returns True."""
        assert is_personalized_query("учитывая мои требования") is True

    def test_russian_marker_pod_moi(self):
        """Test query with 'под мои' marker returns True."""
        assert is_personalized_query("под мои критерии") is True

    def test_russian_marker_kak_v_proshly_raz(self):
        """Test query with 'как в прошлый раз' marker returns True."""
        assert is_personalized_query("как в прошлый раз") is True


class TestBuildPromptExtended:
    """Additional tests for _build_prompt edge cases."""

    @pytest.fixture
    def personalizer(self):
        return CESCPersonalizer(MagicMock())

    def test_build_prompt_includes_property_types(self, personalizer):
        """Test prompt includes property_types from preferences."""
        context = {"preferences": {"property_types": ["apartment", "studio"]}}

        prompt = personalizer._build_prompt("response", context)

        assert "apartment" in prompt
        assert "studio" in prompt

    def test_build_prompt_default_budget(self, personalizer):
        """Test prompt uses default budget when not specified."""
        context = {"preferences": {}}

        prompt = personalizer._build_prompt("response", context)

        assert "не указан" in prompt


class TestShouldPersonalizeExtended:
    """Additional tests for should_personalize edge cases."""

    @pytest.fixture
    def personalizer(self):
        return CESCPersonalizer(MagicMock())

    def test_should_personalize_with_multiple_prefs(self, personalizer):
        """Test returns True when multiple preferences exist."""
        context = {"preferences": {"cities": ["Бургас"], "budget_max": 50000}}

        assert personalizer.should_personalize(context) is True

    def test_should_personalize_empty_cities_list(self, personalizer):
        """Test returns False when cities list is empty."""
        context = {"preferences": {"cities": []}}

        assert personalizer.should_personalize(context) is False

    def test_should_personalize_zero_budget(self, personalizer):
        """Test returns False when budget is 0."""
        context = {"preferences": {"budget_max": 0}}

        assert personalizer.should_personalize(context) is False
