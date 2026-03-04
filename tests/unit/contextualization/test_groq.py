"""Unit tests for GroqContextualizer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.contextualization.base import ContextualizedChunk


class TestGroqContextualizerInit:
    """Tests for GroqContextualizer.__init__."""

    def test_init_with_default_settings(self):
        """Test initialization with default settings."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq") as MockGroq,
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-api-key"
            mock_settings.temperature = 0.0
            MockSettings.return_value = mock_settings

            from src.contextualization.groq import GroqContextualizer

            contextualizer = GroqContextualizer()

            assert contextualizer.settings == mock_settings
            assert contextualizer.total_tokens == 0
            MockAsyncGroq.assert_called_once_with(api_key="test-api-key")
            MockGroq.assert_called_once_with(api_key="test-api-key")

    def test_init_with_custom_settings(self):
        """Test initialization with custom settings object."""
        with (
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq") as MockGroq,
        ):
            custom_settings = MagicMock()
            custom_settings.groq_api_key = "custom-key"
            custom_settings.temperature = 0.5

            from src.contextualization.groq import GroqContextualizer

            contextualizer = GroqContextualizer(settings=custom_settings)

            assert contextualizer.settings == custom_settings
            MockAsyncGroq.assert_called_once_with(api_key="custom-key")
            MockGroq.assert_called_once_with(api_key="custom-key")

    def test_init_creates_both_clients(self):
        """Test that both async and sync clients are created."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq") as MockGroq,
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            MockSettings.return_value = mock_settings

            mock_async_client = MagicMock()
            mock_sync_client = MagicMock()
            MockAsyncGroq.return_value = mock_async_client
            MockGroq.return_value = mock_sync_client

            from src.contextualization.groq import GroqContextualizer

            contextualizer = GroqContextualizer()

            assert contextualizer.client == mock_async_client
            assert contextualizer.sync_client == mock_sync_client


class TestGroqContextualizerContextualize:
    """Tests for GroqContextualizer.contextualize method."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq"),
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.0
            MockSettings.return_value = mock_settings

            mock_client = AsyncMock()
            MockAsyncGroq.return_value = mock_client

            from src.contextualization.groq import GroqContextualizer

            ctx = GroqContextualizer()
            ctx.client = mock_client
            return ctx

    async def test_contextualize_single_chunk(self, contextualizer):
        """Test contextualizing a single chunk."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary of chunk"))]
        mock_response.usage = MagicMock(total_tokens=100)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        chunks = ["This is a legal document about property rights."]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 1
        assert isinstance(results[0], ContextualizedChunk)
        assert results[0].original_text == chunks[0]
        assert results[0].contextual_summary == "Summary of chunk"
        assert results[0].article_number == "chunk_0"
        assert results[0].context_method == "groq"

    async def test_contextualize_multiple_chunks(self, contextualizer):
        """Test contextualizing multiple chunks."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        chunks = ["Chunk 1 text", "Chunk 2 text", "Chunk 3 text"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 3
        assert results[0].article_number == "chunk_0"
        assert results[1].article_number == "chunk_1"
        assert results[2].article_number == "chunk_2"
        assert contextualizer.client.chat.completions.create.call_count == 3

    async def test_contextualize_with_query(self, contextualizer):
        """Test contextualizing with an optional query parameter."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Query-focused summary"))]
        mock_response.usage = MagicMock(total_tokens=75)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        chunks = ["Document about property sale procedures."]
        results = await contextualizer.contextualize(chunks, query="property sale")

        assert len(results) == 1
        assert results[0].contextual_summary == "Query-focused summary"

    async def test_contextualize_empty_chunks(self, contextualizer):
        """Test contextualizing with empty chunks list."""
        results = await contextualizer.contextualize([])

        assert results == []
        contextualizer.client.chat.completions.create.assert_not_called()

    async def test_contextualize_handles_error_gracefully(self, contextualizer):
        """Test that errors in individual chunks are handled gracefully."""
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("API rate limit exceeded")
            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content="Success summary"))]
            response.usage = MagicMock(total_tokens=50)
            return response

        contextualizer.client.chat.completions.create = mock_create

        chunks = ["Chunk 1", "Chunk 2 (will fail)", "Chunk 3"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 3
        assert results[0].contextual_summary == "Success summary"
        # Failed chunk should have empty summary and context_method="none"
        assert results[1].contextual_summary == ""
        assert results[1].context_method == "none"
        assert results[2].contextual_summary == "Success summary"

    async def test_contextualize_uses_parallel_batch_path(self, contextualizer):
        """contextualize() should delegate to contextualize_batch()."""
        expected = [
            ContextualizedChunk(
                original_text="Chunk 1",
                contextual_summary="ctx",
                article_number="chunk_0",
                context_method="groq",
            )
        ]
        batch = AsyncMock(return_value=expected)

        with patch.object(contextualizer, "contextualize_batch", batch):
            results = await contextualizer.contextualize(["Chunk 1"], query="q")

        batch.assert_awaited_once_with(["Chunk 1"], query="q")
        assert results == expected


class TestGroqContextualizerContextualizeSingle:
    """Tests for GroqContextualizer.contextualize_single method."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq"),
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.7
            MockSettings.return_value = mock_settings

            mock_client = AsyncMock()
            MockAsyncGroq.return_value = mock_client

            from src.contextualization.groq import GroqContextualizer

            ctx = GroqContextualizer()
            ctx.client = mock_client
            return ctx

    async def test_contextualize_single_success(self, contextualizer):
        """Test successful single chunk contextualization."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Legal summary"))]
        mock_response.usage = MagicMock(total_tokens=120)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await contextualizer.contextualize_single(
            text="Article 51 of the Criminal Code states...",
            article_number="article_51",
            query="criminal penalties",
        )

        assert isinstance(result, ContextualizedChunk)
        assert result.original_text == "Article 51 of the Criminal Code states..."
        assert result.contextual_summary == "Legal summary"
        assert result.article_number == "article_51"
        assert result.context_method == "groq"

    async def test_contextualize_single_uses_correct_model(self, contextualizer):
        """Test that the correct Groq model is used."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single("Text", "art_1")

        call_args = contextualizer.client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "llama3-70b-8192"
        assert call_args.kwargs["max_tokens"] == 256

    async def test_contextualize_single_uses_settings_temperature(self, contextualizer):
        """Test that temperature from settings is used."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single("Text", "art_1")

        call_args = contextualizer.client.chat.completions.create.call_args
        assert call_args.kwargs["temperature"] == 0.7  # From fixture settings

    async def test_contextualize_single_sends_correct_messages(self, contextualizer):
        """Test that correct system and user prompts are sent."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(
            text="Property law text", article_number="prop_1", query="ownership rights"
        )

        call_args = contextualizer.client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "legal document analyzer" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "Property law text" in messages[1]["content"]
        assert "ownership rights" in messages[1]["content"]

    async def test_contextualize_single_tracks_tokens(self, contextualizer):
        """Test that tokens are tracked correctly."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=150)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        assert contextualizer.total_tokens == 0

        await contextualizer.contextualize_single("Text 1", "art_1")
        assert contextualizer.total_tokens == 150

        await contextualizer.contextualize_single("Text 2", "art_2")
        assert contextualizer.total_tokens == 300

    async def test_contextualize_single_without_usage_attribute(self, contextualizer):
        """Test handling response without usage attribute."""
        mock_response = MagicMock(spec=[])  # No attributes
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        # Explicitly remove usage attribute
        del mock_response.usage
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await contextualizer.contextualize_single("Text", "art_1")

        assert result.contextual_summary == "Summary"
        assert contextualizer.total_tokens == 0  # Not incremented


class TestGroqContextualizerSync:
    """Tests for GroqContextualizer.contextualize_sync method."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq"),
            patch("src.contextualization.groq.Groq") as MockGroq,
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.3
            MockSettings.return_value = mock_settings

            mock_sync_client = MagicMock()
            MockGroq.return_value = mock_sync_client

            from src.contextualization.groq import GroqContextualizer

            ctx = GroqContextualizer()
            ctx.sync_client = mock_sync_client
            return ctx

    def test_contextualize_sync_success(self, contextualizer):
        """Test successful synchronous contextualization."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Sync summary"))]
        mock_response.usage = MagicMock(total_tokens=80)
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        result = contextualizer.contextualize_sync(
            text="Criminal code article text", article_number="crim_42", query="theft penalties"
        )

        assert isinstance(result, ContextualizedChunk)
        assert result.original_text == "Criminal code article text"
        assert result.contextual_summary == "Sync summary"
        assert result.article_number == "crim_42"
        assert result.context_method == "groq"

    def test_contextualize_sync_uses_correct_parameters(self, contextualizer):
        """Test that sync method uses correct API parameters."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        contextualizer.contextualize_sync("Text", "art_1")

        call_args = contextualizer.sync_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "llama3-70b-8192"
        assert call_args.kwargs["max_tokens"] == 256
        assert call_args.kwargs["temperature"] == 0.3

    def test_contextualize_sync_tracks_tokens(self, contextualizer):
        """Test that sync method tracks tokens correctly."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=200)
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        assert contextualizer.total_tokens == 0

        contextualizer.contextualize_sync("Text", "art_1")
        assert contextualizer.total_tokens == 200

    def test_contextualize_sync_without_query(self, contextualizer):
        """Test sync contextualization without query parameter."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        result = contextualizer.contextualize_sync(
            text="Document text", article_number="doc_1", query=None
        )

        assert result.contextual_summary == "Summary"
        call_args = contextualizer.sync_client.chat.completions.create.call_args
        user_message = call_args.kwargs["messages"][1]["content"]
        assert "User is searching for:" not in user_message

    def test_contextualize_sync_without_usage_attribute(self, contextualizer):
        """Test sync handling response without usage attribute."""
        mock_response = MagicMock(spec=[])
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        result = contextualizer.contextualize_sync("Text", "art_1")

        assert result.contextual_summary == "Summary"
        assert contextualizer.total_tokens == 0


class TestGroqContextualizerGetStats:
    """Tests for GroqContextualizer.get_stats method."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq"),
            patch("src.contextualization.groq.Groq"),
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.0
            MockSettings.return_value = mock_settings

            from src.contextualization.groq import GroqContextualizer

            return GroqContextualizer()

    def test_get_stats_initial_values(self, contextualizer):
        """Test stats with no contextualization performed."""
        stats = contextualizer.get_stats()

        assert stats == {
            "total_tokens": 0,
            "total_cost_usd": 0.0,
        }

    def test_get_stats_after_processing(self, contextualizer):
        """Test stats after processing some chunks."""
        contextualizer.total_tokens = 1500

        stats = contextualizer.get_stats()

        assert stats == {
            "total_tokens": 1500,
            "total_cost_usd": 0.0,  # Groq is free
        }

    def test_get_stats_groq_is_free(self, contextualizer):
        """Test that Groq always reports zero cost."""
        contextualizer.total_tokens = 1000000  # Even with many tokens

        stats = contextualizer.get_stats()

        assert stats["total_cost_usd"] == 0.0  # Still free


class TestGroqContextualizerErrorHandling:
    """Tests for error handling in GroqContextualizer."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq"),
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.0
            MockSettings.return_value = mock_settings

            mock_client = AsyncMock()
            MockAsyncGroq.return_value = mock_client

            from src.contextualization.groq import GroqContextualizer

            ctx = GroqContextualizer()
            ctx.client = mock_client
            return ctx

    async def test_api_error_in_contextualize_single(self, contextualizer):
        """Test that API errors propagate from contextualize_single."""
        contextualizer.client.chat.completions.create = AsyncMock(
            side_effect=Exception("Groq API error")
        )

        with pytest.raises(Exception, match="Groq API error"):
            await contextualizer.contextualize_single("Text", "art_1")

    async def test_rate_limit_error(self, contextualizer):
        """Test handling of rate limit errors."""
        contextualizer.client.chat.completions.create = AsyncMock(
            side_effect=Exception("Rate limit exceeded")
        )

        with pytest.raises(Exception, match="Rate limit exceeded"):
            await contextualizer.contextualize_single("Text", "art_1")

    async def test_network_error(self, contextualizer):
        """Test handling of network errors."""
        contextualizer.client.chat.completions.create = AsyncMock(
            side_effect=ConnectionError("Network unreachable")
        )

        with pytest.raises(ConnectionError, match="Network unreachable"):
            await contextualizer.contextualize_single("Text", "art_1")

    async def test_batch_continues_after_single_failure(self, contextualizer, caplog):
        """Test that batch processing continues after individual failures."""
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Request timeout")
            if call_count == 3:
                raise ValueError("Invalid input")
            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content="Success"))]
            response.usage = MagicMock(total_tokens=50)
            return response

        contextualizer.client.chat.completions.create = mock_create
        caplog.set_level("WARNING")

        chunks = ["Chunk 1", "Chunk 2", "Chunk 3", "Chunk 4"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 4
        # Chunk 0 failed
        assert results[0].contextual_summary == ""
        assert results[0].context_method == "none"
        # Chunk 1 succeeded
        assert results[1].contextual_summary == "Success"
        assert results[1].context_method == "groq"
        # Chunk 2 failed
        assert results[2].contextual_summary == ""
        assert results[2].context_method == "none"
        # Chunk 3 succeeded
        assert results[3].contextual_summary == "Success"
        assert results[3].context_method == "groq"

        assert "chunk 0" in caplog.text
        assert "chunk 2" in caplog.text


class TestGroqContextualizerPrompts:
    """Tests for prompt generation in GroqContextualizer."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq"),
            patch("src.contextualization.groq.Groq"),
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.0
            MockSettings.return_value = mock_settings

            from src.contextualization.groq import GroqContextualizer

            return GroqContextualizer()

    def test_get_system_prompt(self, contextualizer):
        """Test system prompt content."""
        prompt = contextualizer.get_system_prompt()

        assert "legal document analyzer" in prompt
        assert "Ukrainian law" in prompt
        assert "contextual summaries" in prompt
        assert "max 100 words" in prompt

    def test_get_user_prompt_without_query(self, contextualizer):
        """Test user prompt without query."""
        prompt = contextualizer.get_user_prompt("Sample legal text")

        assert "Sample legal text" in prompt
        assert "Summarize this legal text" in prompt
        assert "User is searching for:" not in prompt

    def test_get_user_prompt_with_query(self, contextualizer):
        """Test user prompt with query."""
        prompt = contextualizer.get_user_prompt("Sample legal text", query="theft penalties")

        assert "Sample legal text" in prompt
        assert "User is searching for: theft penalties" in prompt


class TestContextualizedChunkIntegration:
    """Integration tests for ContextualizedChunk creation."""

    @pytest.fixture
    def contextualizer(self):
        """Create GroqContextualizer with mocked clients."""
        with (
            patch("src.contextualization.groq.Settings") as MockSettings,
            patch("src.contextualization.groq.AsyncGroq") as MockAsyncGroq,
            patch("src.contextualization.groq.Groq"),
        ):
            mock_settings = MagicMock()
            mock_settings.groq_api_key = "test-key"
            mock_settings.temperature = 0.0
            MockSettings.return_value = mock_settings

            mock_client = AsyncMock()
            MockAsyncGroq.return_value = mock_client

            from src.contextualization.groq import GroqContextualizer

            ctx = GroqContextualizer()
            ctx.client = mock_client
            return ctx

    async def test_contextualized_chunk_full_text_property(self, contextualizer):
        """Test that ContextualizedChunk.full_text combines summary and original."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Legal summary here"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await contextualizer.contextualize_single(
            text="Original document text", article_number="art_1"
        )

        assert result.full_text == "Legal summary here\n\nOriginal document text"

    async def test_contextualized_chunk_to_dict(self, contextualizer):
        """Test that ContextualizedChunk.to_dict works correctly."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(total_tokens=50)
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await contextualizer.contextualize_single(
            text="Original text", article_number="art_1"
        )

        result_dict = result.to_dict()

        assert result_dict["original_text"] == "Original text"
        assert result_dict["contextual_summary"] == "Summary"
        assert result_dict["article_number"] == "art_1"
        assert result_dict["context_method"] == "groq"
        assert "timestamp" in result_dict
        assert result_dict["full_text"] == "Summary\n\nOriginal text"
