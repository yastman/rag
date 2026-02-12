"""Tests for custom vectorizers."""

import pytest


try:
    from redisvl.utils.vectorize import BaseVectorizer  # noqa: F401
except (ImportError, ModuleNotFoundError, ValueError):
    pytest.skip("redisvl not installed", allow_module_level=True)

from unittest.mock import AsyncMock, MagicMock

import httpx

from telegram_bot.services.vectorizers import UserBaseVectorizer


class TestUserBaseVectorizer:
    """Tests for UserBaseVectorizer."""

    def test_init_with_default_url(self):
        """Should initialize with default USER-base URL."""
        vectorizer = UserBaseVectorizer()
        assert vectorizer.base_url == "http://localhost:8003"
        assert vectorizer.dims == 768

    def test_init_with_custom_url(self):
        """Should accept custom URL."""
        vectorizer = UserBaseVectorizer(base_url="http://user-base:8003")
        assert vectorizer.base_url == "http://user-base:8003"

    def test_init_with_custom_timeout(self):
        """Should accept custom timeout."""
        vectorizer = UserBaseVectorizer(timeout=10.0)
        assert vectorizer.timeout == 10.0

    async def test_get_client_creates_httpx_client(self):
        """Should create httpx.AsyncClient on first call."""
        vectorizer = UserBaseVectorizer()
        assert vectorizer._async_client is None

        client = await vectorizer._get_async_client()

        assert client is not None
        assert isinstance(client, httpx.AsyncClient)
        assert vectorizer._async_client is client

        # Cleanup
        await vectorizer.aclose()

    async def test_get_client_reuses_existing_client(self):
        """Should reuse existing client on subsequent calls."""
        vectorizer = UserBaseVectorizer()

        client1 = await vectorizer._get_async_client()
        client2 = await vectorizer._get_async_client()

        assert client1 is client2

        # Cleanup
        await vectorizer.aclose()

    async def test_aembed_single_text(self):
        """Should return 768-dim embedding for single text."""
        vectorizer = UserBaseVectorizer()

        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1] * 768}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        vectorizer._async_client = mock_client

        result = await vectorizer.aembed("тестовый запрос")

        assert len(result) == 768
        assert result == [0.1] * 768
        mock_client.post.assert_called_once_with("/embed", json={"text": "тестовый запрос"})

    async def test_aembed_many_returns_multiple_embeddings(self):
        """Should return embeddings for multiple texts."""
        vectorizer = UserBaseVectorizer()

        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": [[0.1] * 768, [0.2] * 768]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        vectorizer._async_client = mock_client

        texts = ["текст один", "текст два"]
        result = await vectorizer.aembed_many(texts)

        assert len(result) == 2
        assert len(result[0]) == 768
        assert len(result[1]) == 768
        mock_client.post.assert_called_once_with("/embed_batch", json={"texts": texts})

    def test_embed_sync_wrapper(self):
        """Should use sync httpx client to get embedding."""
        vectorizer = UserBaseVectorizer()

        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1] * 768}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        vectorizer._sync_client = mock_client

        result = vectorizer.embed("тест")

        assert result == [0.1] * 768
        mock_client.post.assert_called_once_with("/embed", json={"text": "тест"})

    def test_embed_many_sync_wrapper(self):
        """Should use sync httpx client to get embeddings."""
        vectorizer = UserBaseVectorizer()

        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": [[0.1] * 768, [0.2] * 768]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        vectorizer._sync_client = mock_client

        result = vectorizer.embed_many(["тест1", "тест2"])

        assert len(result) == 2
        mock_client.post.assert_called_once_with("/embed_batch", json={"texts": ["тест1", "тест2"]})

    async def test_aclose_closes_client(self):
        """Should close httpx clients and set to None."""
        vectorizer = UserBaseVectorizer()

        # Create async client
        mock_async_client = AsyncMock()
        vectorizer._async_client = mock_async_client

        # Create sync client
        mock_sync_client = MagicMock()
        vectorizer._sync_client = mock_sync_client

        await vectorizer.aclose()

        mock_async_client.aclose.assert_called_once()
        mock_sync_client.close.assert_called_once()
        assert vectorizer._async_client is None
        assert vectorizer._sync_client is None

    async def test_aclose_does_nothing_if_no_client(self):
        """Should not raise if clients are None."""
        vectorizer = UserBaseVectorizer()
        assert vectorizer._async_client is None
        assert vectorizer._sync_client is None

        # Should not raise
        await vectorizer.aclose()

        assert vectorizer._async_client is None
        assert vectorizer._sync_client is None


class TestUserBaseVectorizerRedisVL:
    """Tests for RedisVL compatibility."""

    def test_has_redisvl_interface(self):
        """Should implement RedisVL vectorizer interface."""
        vectorizer = UserBaseVectorizer()

        # RedisVL expects these methods
        assert hasattr(vectorizer, "embed")
        assert hasattr(vectorizer, "embed_many")
        assert callable(vectorizer.embed)
        assert callable(vectorizer.embed_many)

    def test_dims_property(self):
        """Should expose dims for RedisVL SemanticCache."""
        vectorizer = UserBaseVectorizer()
        assert vectorizer.dims == 768
