"""Tests for HyDE (Hypothetical Document Embeddings) functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.services.query_preprocessor import HyDEGenerator, QueryPreprocessor


class TestQueryPreprocessorHyDE:
    """Tests for HyDE-related methods in QueryPreprocessor."""

    def test_count_words_simple(self):
        """Test word count for simple query."""
        pp = QueryPreprocessor()
        assert pp.count_words("квартира у моря") == 3

    def test_count_words_single_word(self):
        """Test word count for single word."""
        pp = QueryPreprocessor()
        assert pp.count_words("студия") == 1

    def test_count_words_long_query(self):
        """Test word count for long query."""
        pp = QueryPreprocessor()
        # 9 words in Russian query
        assert pp.count_words("двухкомнатная квартира с видом на море недалеко от центра") == 9

    def test_should_use_hyde_short_query(self):
        """Test HyDE is enabled for short queries."""
        pp = QueryPreprocessor()
        # 2 words < 5 words threshold
        assert pp.should_use_hyde("квартира море") is True

    def test_should_use_hyde_long_query(self):
        """Test HyDE is disabled for long queries."""
        pp = QueryPreprocessor()
        # 6 words >= 5 words threshold
        assert pp.should_use_hyde("двухкомнатная квартира в центре Несебра дешево") is False

    def test_should_use_hyde_exact_query(self):
        """Test HyDE is disabled for exact identifier queries."""
        pp = QueryPreprocessor()
        # Even short query with ID should not use HyDE
        assert pp.should_use_hyde("ID 12345") is False

    def test_should_use_hyde_corpus_query(self):
        """Test HyDE is disabled for корпус queries."""
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("корпус 5") is False

    def test_should_use_hyde_custom_threshold(self):
        """Test HyDE with custom word threshold."""
        pp = QueryPreprocessor()
        # 3 words, threshold 4 -> should use HyDE
        assert pp.should_use_hyde("квартира у моря", min_words=4) is True
        # 3 words, threshold 3 -> should NOT use HyDE
        assert pp.should_use_hyde("квартира у моря", min_words=3) is False

    def test_analyze_includes_hyde_fields(self):
        """Test analyze returns HyDE-related fields."""
        pp = QueryPreprocessor()
        result = pp.analyze("студия")

        assert "use_hyde" in result
        assert "word_count" in result

    def test_analyze_hyde_disabled_by_default(self):
        """Test analyze has HyDE disabled when use_hyde=False."""
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=False)

        assert result["use_hyde"] is False

    def test_analyze_hyde_enabled_for_short_query(self):
        """Test analyze enables HyDE for short queries when flag is on."""
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=True, hyde_min_words=5)

        assert result["use_hyde"] is True
        assert result["word_count"] == 1

    def test_analyze_hyde_disabled_for_long_query(self):
        """Test analyze disables HyDE for long queries even when flag is on."""
        pp = QueryPreprocessor()
        result = pp.analyze(
            "двухкомнатная квартира с видом на море недорого",
            use_hyde=True,
            hyde_min_words=5,
        )

        assert result["use_hyde"] is False
        assert result["word_count"] == 7

    def test_analyze_hyde_disabled_for_exact_query(self):
        """Test analyze disables HyDE for exact queries even when flag is on."""
        pp = QueryPreprocessor()
        result = pp.analyze("корпус 5", use_hyde=True, hyde_min_words=5)

        assert result["use_hyde"] is False
        assert result["is_exact"] is True


class TestHyDEGenerator:
    """Tests for HyDEGenerator class."""

    def test_init_defaults(self):
        """Test HyDEGenerator initialization with defaults."""
        hyde = HyDEGenerator()

        assert hyde.api_key == "not-needed"
        assert hyde.base_url == "http://localhost:4000"
        assert hyde.model == "gpt-4o-mini"
        assert hyde._owns_client is True

    def test_init_custom_params(self):
        """Test HyDEGenerator initialization with custom parameters."""
        hyde = HyDEGenerator(
            api_key="test-key",
            base_url="http://custom:5000/",
            model="gpt-4o",
        )

        assert hyde.api_key == "test-key"
        assert hyde.base_url == "http://custom:5000"
        assert hyde.model == "gpt-4o"

    def test_init_with_injected_client(self):
        """Test HyDEGenerator with injected httpx client."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        hyde = HyDEGenerator(client=mock_client)

        assert hyde.client is mock_client
        assert hyde._owns_client is False

    @pytest.mark.asyncio
    async def test_generate_hypothetical_document_success(self):
        """Test successful hypothetical document generation."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Уютная квартира в Несебре, 45м², рядом с пляжем."
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch("telegram_bot.services.query_preprocessor.get_client") as mock_langfuse:
            mock_langfuse.return_value = MagicMock()

            hyde = HyDEGenerator(client=mock_client)
            result = await hyde.generate_hypothetical_document("квартира у моря")

        assert "Несебре" in result or "квартира" in result.lower()
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_hypothetical_document_fallback_on_error(self):
        """Test fallback to original query on error."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Connection timeout")

        with patch("telegram_bot.services.query_preprocessor.get_client") as mock_langfuse:
            mock_langfuse.return_value = MagicMock()

            hyde = HyDEGenerator(client=mock_client)
            result = await hyde.generate_hypothetical_document("квартира у моря")

        # Should return original query on failure
        assert result == "квартира у моря"

    @pytest.mark.asyncio
    async def test_generate_hypothetical_document_api_call_structure(self):
        """Test API call has correct structure."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch("telegram_bot.services.query_preprocessor.get_client") as mock_langfuse:
            mock_langfuse.return_value = MagicMock()

            hyde = HyDEGenerator(
                api_key="test-key",
                base_url="http://test:4000",
                model="test-model",
                client=mock_client,
            )
            await hyde.generate_hypothetical_document("test query")

        # Verify API call structure
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://test:4000/chat/completions"

        json_body = call_args[1]["json"]
        assert json_body["model"] == "test-model"
        assert json_body["temperature"] == 0.7
        assert json_body["max_tokens"] == 200
        assert len(json_body["messages"]) == 2
        assert json_body["messages"][0]["role"] == "system"
        assert json_body["messages"][1]["role"] == "user"
        assert "test query" in json_body["messages"][1]["content"]

    @pytest.mark.asyncio
    async def test_close_owned_client(self):
        """Test close() closes owned client."""
        hyde = HyDEGenerator()
        mock_aclose = AsyncMock()
        hyde.client.aclose = mock_aclose

        await hyde.close()

        mock_aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_injected_client_not_closed(self):
        """Test close() doesn't close injected client."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.aclose = AsyncMock()

        hyde = HyDEGenerator(client=mock_client)
        await hyde.close()

        mock_client.aclose.assert_not_called()


class TestHyDEIntegration:
    """Integration tests for HyDE with QueryPreprocessor."""

    def test_hyde_workflow_short_semantic_query(self):
        """Test HyDE workflow for short semantic query."""
        pp = QueryPreprocessor()

        # Short semantic query should use HyDE
        result = pp.analyze("квартира море", use_hyde=True, hyde_min_words=5)

        assert result["use_hyde"] is True
        assert result["word_count"] == 2
        assert result["is_exact"] is False

    def test_hyde_workflow_short_exact_query(self):
        """Test HyDE workflow for short exact query."""
        pp = QueryPreprocessor()

        # Short but exact query should NOT use HyDE
        result = pp.analyze("ID 12345", use_hyde=True, hyde_min_words=5)

        assert result["use_hyde"] is False
        assert result["is_exact"] is True

    def test_hyde_workflow_long_query(self):
        """Test HyDE workflow for long query."""
        pp = QueryPreprocessor()

        # Long query should NOT use HyDE (already has context)
        # 8 words in Russian query
        result = pp.analyze(
            "ищу двухкомнатную квартиру в Несебре рядом с морем",
            use_hyde=True,
            hyde_min_words=5,
        )

        assert result["use_hyde"] is False
        assert result["word_count"] == 8

    def test_hyde_disabled_globally(self):
        """Test HyDE disabled when global flag is off."""
        pp = QueryPreprocessor()

        # Even short query won't use HyDE if disabled globally
        result = pp.analyze("студия", use_hyde=False, hyde_min_words=5)

        assert result["use_hyde"] is False

    def test_analyze_backward_compatible(self):
        """Test analyze() is backward compatible without HyDE params."""
        pp = QueryPreprocessor()

        # Call without new parameters (backward compatibility)
        result = pp.analyze("квартира в Бургасе")

        # Should work and default to hyde disabled
        assert "original_query" in result
        assert "normalized_query" in result
        assert result["use_hyde"] is False


class TestHyDESystemPrompt:
    """Tests for HyDE system prompt configuration."""

    def test_system_prompt_in_russian(self):
        """Test system prompt is in Russian."""
        assert "Ты" in HyDEGenerator.HYDE_SYSTEM_PROMPT
        assert "недвижимости" in HyDEGenerator.HYDE_SYSTEM_PROMPT

    def test_system_prompt_has_rules(self):
        """Test system prompt contains rules."""
        assert "ПРАВИЛА" in HyDEGenerator.HYDE_SYSTEM_PROMPT

    def test_system_prompt_has_example(self):
        """Test system prompt contains example."""
        assert "Пример" in HyDEGenerator.HYDE_SYSTEM_PROMPT
        assert "квартира у моря" in HyDEGenerator.HYDE_SYSTEM_PROMPT
