"""Unit tests for OpenAIContextualizer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.contextualization.base import ContextualizedChunk
from src.contextualization.openai import OpenAIContextualizer


pytestmark = pytest.mark.legacy_api


class TestOpenAIContextualizerInit:
    """Tests for OpenAIContextualizer.__init__."""

    def test_init_with_settings(self):
        """Test initialization with provided settings."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-api-key"
        mock_settings.model_name = "gpt-4"

        with (
            patch("src.contextualization.openai.AsyncOpenAI") as mock_async,
            patch("src.contextualization.openai.OpenAI") as mock_sync,
        ):
            contextualizer = OpenAIContextualizer(settings=mock_settings)

            assert contextualizer.settings == mock_settings
            assert contextualizer.total_tokens == 0
            assert contextualizer.total_cost == 0.0
            mock_async.assert_called_once_with(api_key="test-api-key", max_retries=3)
            mock_sync.assert_called_once_with(api_key="test-api-key", max_retries=3)

    def test_init_without_settings_uses_default(self):
        """Test initialization without settings uses default Settings."""
        with patch("src.contextualization.openai.Settings") as mock_settings_class:
            mock_settings = MagicMock()
            mock_settings.openai_api_key = "default-key"
            mock_settings_class.return_value = mock_settings

            with (
                patch("src.contextualization.openai.AsyncOpenAI"),
                patch("src.contextualization.openai.OpenAI"),
            ):
                contextualizer = OpenAIContextualizer()

                mock_settings_class.assert_called_once()
                assert contextualizer.settings == mock_settings

    def test_init_creates_async_client(self):
        """Test that AsyncOpenAI client is created."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-api-key"

        with (
            patch("src.contextualization.openai.AsyncOpenAI") as mock_async,
            patch("src.contextualization.openai.OpenAI"),
        ):
            mock_client = MagicMock()
            mock_async.return_value = mock_client

            contextualizer = OpenAIContextualizer(settings=mock_settings)

            assert contextualizer.client == mock_client

    def test_init_creates_sync_client(self):
        """Test that sync OpenAI client is created."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-api-key"

        with (
            patch("src.contextualization.openai.AsyncOpenAI"),
            patch("src.contextualization.openai.OpenAI") as mock_sync,
        ):
            mock_client = MagicMock()
            mock_sync.return_value = mock_client

            contextualizer = OpenAIContextualizer(settings=mock_settings)

            assert contextualizer.sync_client == mock_client

    def test_init_uses_langfuse_openai_drop_in(self):
        """Test that contextualizer uses langfuse.openai clients for auto-tracing.

        This prevents orphan litellm-acompletion traces by ensuring inner
        completion calls are nested under the active @observe span.
        """
        import importlib

        import src.contextualization.openai as ctx_mod

        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-key"

        with (
            patch("langfuse.openai.AsyncOpenAI") as mock_lf_async,
            patch("langfuse.openai.OpenAI") as mock_lf_sync,
        ):
            mock_lf_async.return_value = MagicMock()
            mock_lf_sync.return_value = MagicMock()

            importlib.reload(ctx_mod)
            ctx_mod.OpenAIContextualizer(settings=mock_settings)

            mock_lf_async.assert_called_once_with(api_key="test-key", max_retries=3)
            mock_lf_sync.assert_called_once_with(api_key="test-key", max_retries=3)


class TestOpenAIContextualizerContextualize:
    """Tests for OpenAIContextualizer.contextualize method."""

    @pytest.fixture
    def contextualizer(self):
        """Create OpenAIContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-key"
        mock_settings.model_name = "gpt-4"
        mock_settings.temperature = 0.0

        with (
            patch("src.contextualization.openai.AsyncOpenAI"),
            patch("src.contextualization.openai.OpenAI"),
        ):
            ctx = OpenAIContextualizer(settings=mock_settings)
            ctx.client = AsyncMock()
            return ctx

    async def test_contextualize_single_chunk(self, contextualizer):
        """Test contextualizing a single chunk."""
        # Mock the API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Contextual summary"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        chunks = ["This is the text to contextualize."]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 1
        assert isinstance(results[0], ContextualizedChunk)
        assert results[0].original_text == chunks[0]
        assert results[0].contextual_summary == "Contextual summary"
        assert results[0].article_number == "chunk_0"
        assert results[0].context_method == "openai"

    async def test_contextualize_multiple_chunks(self, contextualizer):
        """Test contextualizing multiple chunks."""
        # Mock responses for each chunk
        mock_responses = []
        for i in range(3):
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = f"Summary {i}"
            resp.usage.prompt_tokens = 100
            resp.usage.completion_tokens = 50
            resp.usage.total_tokens = 150
            mock_responses.append(resp)

        contextualizer.client.chat.completions.create = AsyncMock(side_effect=mock_responses)

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
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Query-aware summary"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        chunks = ["Text"]
        query = "Specific question?"
        results = await contextualizer.contextualize(chunks, query=query)

        assert len(results) == 1
        # Verify the API was called
        contextualizer.client.chat.completions.create.assert_called_once()
        call_kwargs = contextualizer.client.chat.completions.create.call_args[1]
        assert call_kwargs["messages"][1]["role"] == "user"
        assert query in call_kwargs["messages"][1]["content"]

    async def test_contextualize_handles_api_error_gracefully(self, contextualizer):
        """Test that API errors result in fallback chunks."""
        contextualizer.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )

        chunks = ["Text that will fail"]
        results = await contextualizer.contextualize(chunks)

        assert len(results) == 1
        assert results[0].original_text == chunks[0]
        assert results[0].contextual_summary == ""  # Fallback
        assert results[0].context_method == "none"  # Indicates failure

    async def test_contextualize_empty_chunks(self, contextualizer):
        """Test contextualizing empty list returns empty list."""
        results = await contextualizer.contextualize([])
        assert results == []


class TestOpenAIContextualizerContextualizeSingle:
    """Tests for OpenAIContextualizer.contextualize_single method."""

    @pytest.fixture
    def contextualizer(self):
        """Create OpenAIContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-key"
        mock_settings.model_name = "gpt-4"
        mock_settings.temperature = 0.0

        with (
            patch("src.contextualization.openai.AsyncOpenAI"),
            patch("src.contextualization.openai.OpenAI"),
        ):
            ctx = OpenAIContextualizer(settings=mock_settings)
            ctx.client = AsyncMock()
            return ctx

    async def test_contextualize_single_success(self, contextualizer):
        """Test successful single chunk contextualization."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated context"
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 75
        mock_response.usage.total_tokens = 225
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await contextualizer.contextualize_single(
            text="Original text",
            article_number="Article 123",
        )

        assert isinstance(result, ContextualizedChunk)
        assert result.original_text == "Original text"
        assert result.contextual_summary == "Generated context"
        assert result.article_number == "Article 123"
        assert result.context_method == "openai"

    async def test_contextualize_single_tracks_tokens(self, contextualizer):
        """Test that token usage is tracked."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 300
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        initial_tokens = contextualizer.total_tokens
        await contextualizer.contextualize_single(text="Text", article_number="A1")

        assert contextualizer.total_tokens == initial_tokens + 300

    async def test_contextualize_single_tracks_cost(self, contextualizer):
        """Test that cost estimation is tracked."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 100
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        initial_cost = contextualizer.total_cost
        await contextualizer.contextualize_single(text="Text", article_number="A1")

        # Expected: (1000 * 5 + 100 * 15) / 1_000_000 = 0.0065
        expected_cost = (1000 * 5 + 100 * 15) / 1_000_000
        assert contextualizer.total_cost == pytest.approx(initial_cost + expected_cost)

    async def test_contextualize_single_uses_correct_model(self, contextualizer):
        """Test that the correct model is used from settings."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(text="Text", article_number="A1")

        call_kwargs = contextualizer.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == contextualizer.settings.model_name

    async def test_contextualize_single_with_query(self, contextualizer):
        """Test that query is included in user prompt."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        contextualizer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await contextualizer.contextualize_single(
            text="Text",
            article_number="A1",
            query="Query text",
        )

        call_kwargs = contextualizer.client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        user_content = messages[1]["content"]
        assert "Query text" in user_content


class TestOpenAIContextualizerSync:
    """Tests for OpenAIContextualizer.contextualize_sync method."""

    @pytest.fixture
    def contextualizer(self):
        """Create OpenAIContextualizer with mocked clients."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-key"
        mock_settings.model_name = "gpt-4"
        mock_settings.temperature = 0.0

        with (
            patch("src.contextualization.openai.AsyncOpenAI"),
            patch("src.contextualization.openai.OpenAI"),
        ):
            ctx = OpenAIContextualizer(settings=mock_settings)
            ctx.sync_client = MagicMock()
            return ctx

    def test_contextualize_sync_success(self, contextualizer):
        """Test successful synchronous contextualization."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sync summary"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        result = contextualizer.contextualize_sync(
            text="Text",
            article_number="Art5",
        )

        assert isinstance(result, ContextualizedChunk)
        assert result.original_text == "Text"
        assert result.contextual_summary == "Sync summary"
        assert result.article_number == "Art5"
        assert result.context_method == "openai"

    def test_contextualize_sync_tracks_tokens(self, contextualizer):
        """Test that sync method also tracks tokens."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary"
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 75
        mock_response.usage.total_tokens = 225
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        initial_tokens = contextualizer.total_tokens
        contextualizer.contextualize_sync(text="Text", article_number="A1")

        assert contextualizer.total_tokens == initial_tokens + 225

    def test_contextualize_sync_with_query(self, contextualizer):
        """Test sync contextualization with query."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Query-aware summary"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        contextualizer.sync_client.chat.completions.create = MagicMock(return_value=mock_response)

        contextualizer.contextualize_sync(
            text="Text",
            article_number="A1",
            query="Query text",
        )

        call_kwargs = contextualizer.sync_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        user_content = messages[1]["content"]
        assert "Query text" in user_content


class TestOpenAIContextualizerGetStats:
    """Tests for OpenAIContextualizer.get_stats method."""

    def test_get_stats_values(self):
        """Test stats reporting."""
        with (
            patch.dict(
                "os.environ",
                {"API_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"},
            ),
            patch("src.contextualization.openai.AsyncOpenAI"),
            patch("src.contextualization.openai.OpenAI"),
        ):
            ctx = OpenAIContextualizer()
            ctx.total_tokens = 1234
            ctx.total_cost = 0.56789

            stats = ctx.get_stats()

            assert stats["total_tokens"] == 1234
            assert stats["total_cost_usd"] == 0.5679  # Rounded


class TestOpenAIContextualizerSDKRetries:
    """Contract: OpenAI SDK native retries replace Tenacity (#1651).

    OpenAI client provides a built-in `max_retries` parameter (default 2)
    that retries connection errors, 408, 409, 429, and >=500 with
    exponential backoff. Tenacity wrapping these calls duplicates retry
    policy and makes behavior harder to reason about (Context7
    /openai/openai-python).
    """

    def test_async_client_initialized_with_max_retries(self):
        """AsyncOpenAI must use 3 retries to preserve four total attempts."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-key"

        with (
            patch("src.contextualization.openai.AsyncOpenAI") as mock_async,
            patch("src.contextualization.openai.OpenAI"),
        ):
            OpenAIContextualizer(settings=mock_settings)

            mock_async.assert_called_once()
            kwargs = mock_async.call_args.kwargs
            assert kwargs.get("api_key") == "test-key"
            assert kwargs.get("max_retries") == 3, (
                "AsyncOpenAI client must be constructed with max_retries=3"
            )

    def test_sync_client_initialized_with_max_retries(self):
        """Sync OpenAI must use 3 retries to preserve four total attempts."""
        mock_settings = MagicMock()
        mock_settings.openai_api_key = "test-key"

        with (
            patch("src.contextualization.openai.AsyncOpenAI"),
            patch("src.contextualization.openai.OpenAI") as mock_sync,
        ):
            OpenAIContextualizer(settings=mock_settings)

            mock_sync.assert_called_once()
            kwargs = mock_sync.call_args.kwargs
            assert kwargs.get("api_key") == "test-key"
            assert kwargs.get("max_retries") == 3

    def test_no_tenacity_retry_decorator_on_methods(self):
        """contextualize_single and contextualize_sync must not use Tenacity @retry."""
        import ast
        import inspect

        from src.contextualization import openai as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)

        offending: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                continue
            if node.name not in {"contextualize_single", "contextualize_sync"}:
                continue
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Name) and target.id == "retry":
                    offending.append(f"{node.name}: @retry(...)")
                if isinstance(target, ast.Attribute) and target.attr == "retry":
                    offending.append(f"{node.name}: @{ast.unparse(target)}(...)")

        assert not offending, (
            "Tenacity @retry decorators must be removed from contextualize_single/sync; "
            "rely on OpenAI client max_retries instead. Offending:\n" + "\n".join(offending)
        )

    def test_module_does_not_import_tenacity(self):
        """The openai contextualizer module must not import tenacity at all."""
        import ast
        import inspect

        from src.contextualization import openai as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)

        bad: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "tenacity":
                bad.append("from tenacity import " + ", ".join(alias.name for alias in node.names))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tenacity":
                        bad.append("import tenacity")

        assert not bad, "Tenacity imports must be removed:\n" + "\n".join(bad)
