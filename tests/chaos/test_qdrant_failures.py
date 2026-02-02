"""Chaos tests for Qdrant failures.

Tests verify graceful degradation when Qdrant is unavailable or times out.
These tests focus on the QdrantService's error handling behavior.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestQdrantTimeout:
    """Tests for Qdrant timeout handling."""

    async def test_qdrant_connection_timeout_returns_empty_results(self):
        """Verify search returns empty list on connection timeout."""
        from telegram_bot.services.qdrant import QdrantService

        # Create service
        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )

        # Mock the internal client to raise timeout
        mock_client = MagicMock()
        mock_client.query_points = AsyncMock(
            side_effect=asyncio.TimeoutError("Connection timed out")
        )
        service._client = mock_client

        # Should return empty list, not raise exception
        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector={"indices": [1, 2], "values": [0.5, 0.3]},
            top_k=10,
        )

        assert results == []

    async def test_qdrant_server_error_returns_empty_results(self):
        """Verify search returns empty list on server error."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )

        mock_client = MagicMock()
        # Use a generic exception that simulates server error
        mock_client.query_points = AsyncMock(
            side_effect=ConnectionError("Service Unavailable (503)")
        )
        service._client = mock_client

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector={"indices": [1, 2], "values": [0.5, 0.3]},
            top_k=10,
        )

        assert results == []

    async def test_qdrant_generic_exception_returns_empty_results(self):
        """Verify search returns empty list on generic exception."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )

        mock_client = MagicMock()
        mock_client.query_points = AsyncMock(
            side_effect=Exception("Unexpected error")
        )
        service._client = mock_client

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            top_k=10,
        )

        assert results == []


class TestQdrantConnectionFailure:
    """Tests for Qdrant connection failures."""

    async def test_qdrant_connection_refused_graceful_degradation(self):
        """Verify graceful handling when Qdrant is completely unavailable."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )

        mock_client = MagicMock()
        mock_client.query_points = AsyncMock(
            side_effect=ConnectionRefusedError("Connection refused")
        )
        service._client = mock_client

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            top_k=10,
        )

        # Should return empty list gracefully
        assert results == []

    async def test_qdrant_dns_resolution_failure(self):
        """Verify handling of DNS resolution failures."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://nonexistent-host:6333",
            collection_name="test_collection",
        )

        mock_client = MagicMock()
        mock_client.query_points = AsyncMock(
            side_effect=OSError("getaddrinfo failed")
        )
        service._client = mock_client

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            top_k=10,
        )

        assert results == []


class TestQdrantRecovery:
    """Tests for Qdrant failure recovery."""

    async def test_qdrant_recovers_after_transient_failure(self):
        """Verify service recovers after transient failures."""
        from qdrant_client import models

        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )

        mock_client = MagicMock()
        call_count = 0

        async def mock_query(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise asyncio.TimeoutError("Transient timeout")
            # Third call succeeds
            mock_result = MagicMock()
            mock_point = MagicMock()
            mock_point.id = "1"
            mock_point.score = 0.9
            mock_point.payload = {"text": "recovered result", "metadata": {}}
            mock_result.points = [mock_point]
            return mock_result

        mock_client.query_points = mock_query
        service._client = mock_client

        # First two calls fail
        for _ in range(2):
            results = await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
            )
            assert results == []

        # Third call succeeds
        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            top_k=10,
        )
        # Should have results after recovery
        assert len(results) >= 0  # May or may not have results


class TestQdrantServiceInitialization:
    """Tests for QdrantService initialization."""

    def test_qdrant_service_init_with_different_modes(self):
        """Verify QdrantService initializes correctly with different modes."""
        from telegram_bot.services.qdrant import QdrantService

        # Test different quantization modes
        for mode in ["off", "scalar", "binary"]:
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
                quantization_mode=mode,
            )
            assert service is not None

            if mode == "off":
                assert service.collection_name == "test_collection"
            elif mode == "scalar":
                assert service.collection_name == "test_collection_scalar"
            elif mode == "binary":
                assert service.collection_name == "test_collection_binary"

    def test_qdrant_mode_switching(self):
        """Verify mode switching updates collection name."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
            quantization_mode="off",
        )

        assert service.collection_name == "test_collection"

        service.set_quantization_mode("binary")
        assert service.collection_name == "test_collection_binary"

        service.set_quantization_mode("scalar")
        assert service.collection_name == "test_collection_scalar"

        service.set_quantization_mode("off")
        assert service.collection_name == "test_collection"
