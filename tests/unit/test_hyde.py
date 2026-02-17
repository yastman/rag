"""Tests for HyDE (Hypothetical Document Embeddings) functionality (OpenAI SDK)."""

from unittest.mock import AsyncMock, MagicMock

import openai

from telegram_bot.services.query_preprocessor import HyDEGenerator, QueryPreprocessor


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


class TestQueryPreprocessorHyDE:
    """Tests for HyDE-related methods in QueryPreprocessor."""

    def test_count_words_simple(self):
        pp = QueryPreprocessor()
        assert pp.count_words("квартира у моря") == 3

    def test_count_words_single_word(self):
        pp = QueryPreprocessor()
        assert pp.count_words("студия") == 1

    def test_count_words_long_query(self):
        pp = QueryPreprocessor()
        assert pp.count_words("двухкомнатная квартира с видом на море недалеко от центра") == 9

    def test_should_use_hyde_short_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("квартира море") is True

    def test_should_use_hyde_long_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("двухкомнатная квартира в центре Несебра дешево") is False

    def test_should_use_hyde_exact_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("ID 12345") is False

    def test_should_use_hyde_corpus_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("корпус 5") is False

    def test_should_use_hyde_custom_threshold(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("квартира у моря", min_words=4) is True
        assert pp.should_use_hyde("квартира у моря", min_words=3) is False

    def test_analyze_includes_hyde_fields(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия")
        assert "use_hyde" in result
        assert "word_count" in result

    def test_analyze_hyde_disabled_by_default(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=False)
        assert result["use_hyde"] is False

    def test_analyze_hyde_enabled_for_short_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is True
        assert result["word_count"] == 1

    def test_analyze_hyde_disabled_for_long_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze(
            "двухкомнатная квартира с видом на море недорого",
            use_hyde=True,
            hyde_min_words=5,
        )
        assert result["use_hyde"] is False
        assert result["word_count"] == 7

    def test_analyze_hyde_disabled_for_exact_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("корпус 5", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is False
        assert result["is_exact"] is True


class TestHyDEGenerator:
    """Tests for HyDEGenerator class (OpenAI SDK)."""

    def test_init_defaults(self):
        hyde = HyDEGenerator()
        assert hyde.api_key == "not-needed"
        assert hyde.base_url == "http://localhost:4000"
        assert hyde.model == "gpt-4o-mini"

    def test_init_custom_params(self):
        hyde = HyDEGenerator(
            api_key="test-key",
            base_url="http://custom:5000/",
            model="gpt-4o",
        )
        assert hyde.api_key == "test-key"
        assert hyde.base_url == "http://custom:5000"
        assert hyde.model == "gpt-4o"

    def test_init_creates_openai_client(self):
        from openai import AsyncOpenAI

        hyde = HyDEGenerator()
        assert isinstance(hyde.client, AsyncOpenAI)

    async def test_generate_hypothetical_document_success(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Уютная квартира в Несебре, 45м², рядом с пляжем.")
        )

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert "Несебре" in result or "квартира" in result.lower()
        hyde.client.chat.completions.create.assert_called_once()

    async def test_generate_hypothetical_document_fallback_on_error(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert result == "квартира у моря"

    async def test_generate_hypothetical_document_fallback_on_generic_error(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(side_effect=Exception("Connection failed"))

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert result == "квартира у моря"

    async def test_generate_hypothetical_document_api_call_structure(self):
        hyde = HyDEGenerator(
            api_key="test-key",
            base_url="http://test:4000",
            model="test-model",
        )
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Test response")
        )

        await hyde.generate_hypothetical_document("test query")

        call_kwargs = hyde.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 200
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"
        assert "test query" in call_kwargs["messages"][1]["content"]

    async def test_close(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()

        await hyde.close()

        hyde.client.close.assert_called_once()

    async def test_generate_handles_none_content(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(return_value=_mock_completion(None))

        result = await hyde.generate_hypothetical_document("квартира")

        # Should fallback to query when content is None
        assert result == "квартира"


class TestHyDEIntegration:
    """Integration tests for HyDE with QueryPreprocessor."""

    def test_hyde_workflow_short_semantic_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("квартира море", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is True
        assert result["word_count"] == 2
        assert result["is_exact"] is False

    def test_hyde_workflow_short_exact_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("ID 12345", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is False
        assert result["is_exact"] is True

    def test_hyde_workflow_long_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze(
            "ищу двухкомнатную квартиру в Несебре рядом с морем",
            use_hyde=True,
            hyde_min_words=5,
        )
        assert result["use_hyde"] is False
        assert result["word_count"] == 8

    def test_hyde_disabled_globally(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=False, hyde_min_words=5)
        assert result["use_hyde"] is False

    def test_analyze_backward_compatible(self):
        pp = QueryPreprocessor()
        result = pp.analyze("квартира в Бургасе")
        assert "original_query" in result
        assert "normalized_query" in result
        assert result["use_hyde"] is False


class TestHyDESystemPrompt:
    """Tests for HyDE system prompt configuration."""

    def test_system_prompt_in_russian(self):
        assert "Ты" in HyDEGenerator.HYDE_SYSTEM_PROMPT
        assert "недвижимости" in HyDEGenerator.HYDE_SYSTEM_PROMPT

    def test_system_prompt_has_rules(self):
        assert "ПРАВИЛА" in HyDEGenerator.HYDE_SYSTEM_PROMPT

    def test_system_prompt_has_example(self):
        assert "Пример" in HyDEGenerator.HYDE_SYSTEM_PROMPT
        assert "квартира у моря" in HyDEGenerator.HYDE_SYSTEM_PROMPT
