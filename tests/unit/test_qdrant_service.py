"""Tests for QdrantService quantization parameters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.qdrant import QdrantService


class TestQdrantServiceQuantization:
    """Test quantization search parameters."""

    @pytest.fixture
    def service(self):
        """Create QdrantService with mocked client."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )
            service._client = AsyncMock()
            return service

    @pytest.mark.asyncio
    async def test_hybrid_search_with_quantization_ignore(self, service):
        """Test that quantization_ignore is passed to search params."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=True,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        assert "search_params" in call_kwargs
        assert call_kwargs["search_params"] is not None

    @pytest.mark.asyncio
    async def test_hybrid_search_default_no_quantization_params(self, service):
        """Test default behavior without quantization params."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.hybrid_search_rrf(dense_vector=[0.1] * 1024)

        call_kwargs = service._client.query_points.call_args.kwargs
        assert call_kwargs.get("search_params") is None

    @pytest.mark.asyncio
    async def test_quantization_params_values(self, service):
        """Test that ignore/rescore/oversampling values are correctly set."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        # Test with specific values
        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=True,
            quantization_rescore=False,
            quantization_oversampling=3.0,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        search_params = call_kwargs["search_params"]

        # Verify all quantization params are correctly passed
        assert search_params is not None
        assert search_params.quantization.ignore is True
        assert search_params.quantization.rescore is False
        assert search_params.quantization.oversampling == 3.0

    @pytest.mark.asyncio
    async def test_quantization_default_rescore_oversampling(self, service):
        """Test default rescore=True and oversampling=2.0."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        # Only set ignore, check defaults for rescore/oversampling
        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=False,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        search_params = call_kwargs["search_params"]

        assert search_params.quantization.ignore is False
        assert search_params.quantization.rescore is True  # default
        assert search_params.quantization.oversampling == 2.0  # default
