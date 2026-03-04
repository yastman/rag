"""Unit tests for ClaudeContextualizer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.contextualization.base import ContextualizedChunk
from src.contextualization.claude import ClaudeContextualizer


class TestClaudeContextualizerInit:
    """Tests for ClaudeContextualizer.__init__."""

    def test_init_with_settings(self):
        """Test initialization with provided settings."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-api-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic") as mock_async,
            patch("src.contextualization.claude.Anthropic") as mock_sync,
        ):
            contextualizer = ClaudeContextualizer(settings=mock_settings)

            assert contextualizer.settings == mock_settings
            assert contextualizer.use_cache is True
            assert contextualizer.total_tokens == 0
            assert contextualizer.total_cost == 0.0
            mock_async.assert_called_once_with(api_key="test-api-key")
            mock_sync.assert_called_once_with(api_key="test-api-key")

    def test_init_without_settings_uses_default(self):
        """Test initialization without settings uses default Settings."""
        with patch("src.contextualization.claude.Settings") as mock_settings_class:
            mock_settings = MagicMock()
            mock_settings.anthropic_api_key = "default-key"
            mock_settings_class.return_value = mock_settings

            with (
                patch("src.contextualization.claude.AsyncAnthropic"),
                patch("src.contextualization.claude.Anthropic"),
            ):
                contextualizer = ClaudeContextualizer()

                mock_settings_class.assert_called_once()
                assert contextualizer.settings == mock_settings

    def test_init_with_cache_disabled(self):
        """Test initialization with caching disabled."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            contextualizer = ClaudeContextualizer(settings=mock_settings, use_cache=False)

            assert contextualizer.use_cache is False

    def test_init_creates_async_client(self):
        """Test that AsyncAnthropic client is created."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-api-key"

        with (
            patch("src.contextualization.claude.AsyncAnthropic") as mock_async,
            patch("src.contextualization.claude.Anthropic"),
        ):
            mock_client = MagicMock()
            mock_async.return_value = mock_client

            contextualizer = ClaudeContextualizer(settings=mock_settings)

            assert contextualizer.client == mock_client

    def test_init_creates_sync_client(self):
        """Test that sync Anthropic client is created."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-api-key"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic") as mock_sync,
        ):
            mock_client = MagicMock()
            mock_sync.return_value = mock_client

            contextualizer = ClaudeContextualizer(settings=mock_settings)

            assert contextualizer.sync_client == mock_client


class TestClaudeContextualizerContextualize:
    """Tests for ClaudeContextualizer.contextualize method."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            ctx = ClaudeContextualizer(settings=mock_settings)
            ctx.client = AsyncMock()
            return ctx

    async def test_contextualize_single_chunk(self, contextualizer):
        """Test contextualizing a single chunk."""
        # Mock the API response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Contextual summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        chunks = ["This is the legal text to contextualize."]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 1
        assert isinstance(results[0], ContextualizedChunk)
        assert results[0].original_text == chunks[0]
        assert results[0].contextual_summary == "Contextual summary"
        assert results[0].article_number == "chunk_0"
        assert results[0].context_method == "claude"

    async def test_contextualize_multiple_chunks(self, contextualizer):
        """Test contextualizing multiple chunks."""
        # Mock responses for each chunk
        mock_responses = []
        for i in range(3):
            resp = MagicMock()
            resp.content = [MagicMock(text=f"Summary {i}")]
            resp.usage.input_tokens = 100
            resp.usage.output_tokens = 50
            mock_responses.append(resp)

        contextualizer.client.messages.create = AsyncMock(side_effect=mock_responses)

        chunks = ["Chunk 1 text", "Chunk 2 text", "Chunk 3 text"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.original_text == chunks[i]
            assert result.contextual_summary == f"Summary {i}"
            assert result.article_number == f"chunk_{i}"

    async def test_contextualize_with_query(self, contextualizer):
        """Test contextualization with optional query parameter."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Query-aware summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        chunks = ["Legal text"]
        query = "What are the penalties?"
        results = await contextualizer.contextualize(chunks, query=query)

        assert len(results) == 1
        # Verify the API was called (query is passed to contextualize_single)
        contextualizer.client.messages.create.assert_called_once()

    async def test_contextualize_handles_api_error_gracefully(self, contextualizer):
        """Test that API errors result in fallback chunks."""
        contextualizer.client.messages.create = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )

        chunks = ["Text that will fail"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 1
        assert results[0].original_text == chunks[0]
        assert results[0].contextual_summary == ""  # Fallback
        assert results[0].context_method == "none"  # Indicates failure

    async def test_contextualize_partial_failure(self, contextualizer):
        """Test that partial failures don't affect successful chunks."""
        # First call succeeds, second fails, third succeeds
        success_response = MagicMock()
        success_response.content = [MagicMock(text="Success summary")]
        success_response.usage.input_tokens = 100
        success_response.usage.output_tokens = 50

        contextualizer.client.messages.create = AsyncMock(
            side_effect=[
                success_response,
                Exception("Temporary failure"),
                success_response,
            ]
        )

        chunks = ["Chunk 1", "Chunk 2", "Chunk 3"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 3
        assert results[0].context_method == "claude"
        assert results[1].context_method == "none"  # Failed
        assert results[2].context_method == "claude"

    async def test_contextualize_empty_chunks(self, contextualizer):
        """Test contextualizing empty list returns empty list."""
        results = await contextualizer.contextualize([])
        assert results == []


class TestClaudeContextualizerContextualizeSingle:
    """Tests for ClaudeContextualizer.contextualize_single method."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            ctx = ClaudeContextualizer(settings=mock_settings)
            ctx.client = AsyncMock()
            return ctx

    async def test_contextualize_single_success(self, contextualizer):
        """Test successful single chunk contextualization."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated context")]
        mock_response.usage.input_tokens = 150
        mock_response.usage.output_tokens = 75
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        result = await contextualizer.contextualize_single(
            text="Original legal text",
            article_number="Article 123",
        )

        assert isinstance(result, ContextualizedChunk)
        assert result.original_text == "Original legal text"
        assert result.contextual_summary == "Generated context"
        assert result.article_number == "Article 123"
        assert result.context_method == "claude"

    async def test_contextualize_single_with_cache_control(self, contextualizer):
        """Test that cache control is on the system= param when use_cache is True."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Cached context")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(text="Text", article_number="Art1")

        call_kwargs = contextualizer.client.messages.create.call_args[1]
        # System param must be a list with cache_control
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        # User content must be a plain string (no cache_control there)
        user_content = call_kwargs["messages"][0]["content"]
        assert isinstance(user_content, str)

    async def test_contextualize_single_without_cache_control(self, contextualizer):
        """Test that system= is a plain string when use_cache is False."""
        contextualizer.use_cache = False
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Non-cached context")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(text="Text", article_number="Art1")

        call_kwargs = contextualizer.client.messages.create.call_args[1]
        system = call_kwargs["system"]
        assert isinstance(system, str)

    async def test_contextualize_single_tracks_tokens(self, contextualizer):
        """Test that token usage is tracked."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 100
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        initial_tokens = contextualizer.total_tokens
        await contextualizer.contextualize_single(text="Text", article_number="A1")

        assert contextualizer.total_tokens == initial_tokens + 300

    async def test_contextualize_single_tracks_cost(self, contextualizer):
        """Test that cost estimation is tracked."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 1000  # $5/MTok = $0.005
        mock_response.usage.output_tokens = 100  # $15/MTok = $0.0015
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        initial_cost = contextualizer.total_cost
        await contextualizer.contextualize_single(text="Text", article_number="A1")

        # Expected: (1000 * 5 + 100 * 15) / 1_000_000 = 0.0065
        expected_cost = (1000 * 5 + 100 * 15) / 1_000_000
        assert contextualizer.total_cost == pytest.approx(initial_cost + expected_cost)

    async def test_contextualize_single_uses_correct_model(self, contextualizer):
        """Test that the correct model is used from settings."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(text="Text", article_number="A1")

        call_kwargs = contextualizer.client.messages.create.call_args[1]
        assert call_kwargs["model"] == contextualizer.settings.model_name

    async def test_contextualize_single_with_query(self, contextualizer):
        """Test that query is included in user prompt."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(
            text="Legal text",
            article_number="A1",
            query="What are the fines?",
        )

        call_kwargs = contextualizer.client.messages.create.call_args[1]
        messages = call_kwargs["messages"]
        # User prompt should be a plain string containing the query
        user_content = messages[0]["content"]
        assert isinstance(user_content, str)
        assert "What are the fines?" in user_content


class TestClaudeContextualizerSync:
    """Tests for ClaudeContextualizer.contextualize_sync method."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            ctx = ClaudeContextualizer(settings=mock_settings)
            ctx.sync_client = MagicMock()
            return ctx

    def test_contextualize_sync_success(self, contextualizer):
        """Test successful synchronous contextualization."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Sync summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.sync_client.messages.create = MagicMock(return_value=mock_response)

        result = contextualizer.contextualize_sync(
            text="Legal text",
            article_number="Art5",
        )

        assert isinstance(result, ContextualizedChunk)
        assert result.original_text == "Legal text"
        assert result.contextual_summary == "Sync summary"
        assert result.article_number == "Art5"
        assert result.context_method == "claude"

    def test_contextualize_sync_tracks_tokens(self, contextualizer):
        """Test that sync method also tracks tokens."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 150
        mock_response.usage.output_tokens = 75
        contextualizer.sync_client.messages.create = MagicMock(return_value=mock_response)

        initial_tokens = contextualizer.total_tokens
        contextualizer.contextualize_sync(text="Text", article_number="A1")

        assert contextualizer.total_tokens == initial_tokens + 225

    def test_contextualize_sync_uses_system_prompt(self, contextualizer):
        """Test that sync method uses system prompt correctly."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.sync_client.messages.create = MagicMock(return_value=mock_response)

        contextualizer.contextualize_sync(text="Text", article_number="A1")

        call_kwargs = contextualizer.sync_client.messages.create.call_args[1]
        assert "system" in call_kwargs
        assert "legal document analyzer" in call_kwargs["system"].lower()

    def test_contextualize_sync_with_query(self, contextualizer):
        """Test sync contextualization with query."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Query-aware summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.sync_client.messages.create = MagicMock(return_value=mock_response)

        contextualizer.contextualize_sync(
            text="Legal text",
            article_number="A1",
            query="imprisonment duration",
        )

        call_kwargs = contextualizer.sync_client.messages.create.call_args[1]
        messages = call_kwargs["messages"]
        user_content = messages[0]["content"]
        assert "imprisonment duration" in user_content


class TestClaudeContextualizerGetStats:
    """Tests for ClaudeContextualizer.get_stats method."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            return ClaudeContextualizer(settings=mock_settings)

    def test_get_stats_initial_values(self, contextualizer):
        """Test stats with no contextualization performed."""
        stats = contextualizer.get_stats()

        assert stats["total_tokens"] == 0
        assert stats["total_cost_usd"] == 0
        assert stats["avg_cost_per_chunk"] == 0

    def test_get_stats_after_processing(self, contextualizer):
        """Test stats after processing some chunks."""
        contextualizer.total_tokens = 1500
        contextualizer.total_cost = 0.015

        stats = contextualizer.get_stats()

        assert stats["total_tokens"] == 1500
        assert stats["total_cost_usd"] == 0.015
        # avg = 0.015 / 1500 * 1000 = 0.01
        assert stats["avg_cost_per_chunk"] == 0.01

    def test_get_stats_rounds_cost(self, contextualizer):
        """Test that cost values are properly rounded."""
        contextualizer.total_tokens = 1000
        contextualizer.total_cost = 0.123456789

        stats = contextualizer.get_stats()

        assert stats["total_cost_usd"] == 0.1235  # Rounded to 4 decimals


class TestClaudeContextualizerPrompts:
    """Tests for prompt generation methods (inherited from base)."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer instance."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            return ClaudeContextualizer(settings=mock_settings)

    def test_get_system_prompt(self, contextualizer):
        """Test system prompt contains required elements."""
        prompt = contextualizer.get_system_prompt()

        assert "legal document analyzer" in prompt.lower()
        assert "summary" in prompt.lower()
        assert "Ukrainian" in prompt

    def test_get_user_prompt_without_query(self, contextualizer):
        """Test user prompt without query."""
        text = "Article 185. Theft is..."
        prompt = contextualizer.get_user_prompt(text)

        assert text in prompt
        assert "Summarize" in prompt

    def test_get_user_prompt_with_query(self, contextualizer):
        """Test user prompt includes query when provided."""
        text = "Article 185. Theft is..."
        query = "What are the penalties for theft?"
        prompt = contextualizer.get_user_prompt(text, query=query)

        assert text in prompt
        assert query in prompt
        assert "searching for" in prompt.lower()


class TestClaudeContextualizerErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            ctx = ClaudeContextualizer(settings=mock_settings)
            ctx.client = AsyncMock()
            return ctx

    async def test_handles_rate_limit_error(self, contextualizer):
        """Test handling of rate limit errors."""
        contextualizer.client.messages.create = AsyncMock(
            side_effect=Exception("Rate limit exceeded")
        )

        results = await contextualizer.contextualize(["Text"])

        assert len(results) == 1
        assert results[0].context_method == "none"

    async def test_handles_network_error(self, contextualizer):
        """Test handling of network errors."""
        contextualizer.client.messages.create = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        results = await contextualizer.contextualize(["Text"])

        assert len(results) == 1
        assert results[0].contextual_summary == ""

    async def test_handles_invalid_response(self, contextualizer):
        """Test handling when response structure is unexpected."""
        mock_response = MagicMock()
        mock_response.content = []  # Empty content
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        # This should raise IndexError when accessing content[0]
        results = await contextualizer.contextualize(["Text"])

        # Should fall back gracefully
        assert len(results) == 1
        assert results[0].context_method == "none"


class TestClaudeContextualizerBatch:
    """Tests for batch processing behavior."""

    @pytest.fixture
    def contextualizer(self):
        """Create ClaudeContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.model_name = "claude-3-sonnet"

        with (
            patch("src.contextualization.claude.AsyncAnthropic"),
            patch("src.contextualization.claude.Anthropic"),
        ):
            ctx = ClaudeContextualizer(settings=mock_settings)
            ctx.client = AsyncMock()
            return ctx

    async def test_batch_processes_sequentially(self, contextualizer):
        """Test that chunks are processed sequentially (not in parallel)."""
        call_order = []

        async def track_calls(*args, **kwargs):
            call_order.append(len(call_order))
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=f"Summary {len(call_order)}")]
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 50
            return mock_response

        contextualizer.client.messages.create = AsyncMock(side_effect=track_calls)

        chunks = ["Chunk A", "Chunk B", "Chunk C"]
        await contextualizer.contextualize(chunks)

        # Verify sequential processing
        assert call_order == [0, 1, 2]

    async def test_batch_accumulates_tokens(self, contextualizer):
        """Test that tokens accumulate across batch processing."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        chunks = ["A", "B", "C", "D", "E"]
        await contextualizer.contextualize(chunks)

        # 5 chunks * 150 tokens each = 750 total
        assert contextualizer.total_tokens == 750

    async def test_batch_accumulates_cost(self, contextualizer):
        """Test that cost accumulates across batch processing."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]
        mock_response.usage.input_tokens = 1000  # $0.005 per chunk
        mock_response.usage.output_tokens = 100  # $0.0015 per chunk
        contextualizer.client.messages.create = AsyncMock(return_value=mock_response)

        chunks = ["A", "B", "C"]
        await contextualizer.contextualize(chunks)

        # Per chunk: (1000*5 + 100*15) / 1M = 0.0065
        # Total: 0.0065 * 3 = 0.0195
        expected_cost = 0.0065 * 3
        assert contextualizer.total_cost == pytest.approx(expected_cost)
