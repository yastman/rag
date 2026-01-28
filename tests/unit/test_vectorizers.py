"""Tests for custom vectorizers."""

from unittest.mock import AsyncMock, patch

import pytest

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

    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        """Should return 768-dim embedding for single text."""
        vectorizer = UserBaseVectorizer()

        mock_response = {"embedding": [0.1] * 768}

        with patch.object(vectorizer, "_client") as mock_client:
            mock_client.post = AsyncMock(
                return_value=AsyncMock(json=lambda: mock_response, raise_for_status=lambda: None)
            )

            result = await vectorizer.aembed("тестовый запрос")

            assert len(result) == 768
            mock_client.post.assert_called_once()

    def test_embed_sync(self):
        """Should provide sync wrapper."""
        vectorizer = UserBaseVectorizer()
        assert hasattr(vectorizer, "embed")


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
