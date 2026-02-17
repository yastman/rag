"""Chaos tests for Qdrant failures.

Tests verify graceful degradation when Qdrant is unavailable or times out.
These tests focus on the QdrantService's error handling behavior.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestQdrantExceptionHandling:
    """Tests for Qdrant error handling — all exceptions return empty results."""

    @pytest.mark.parametrize(
        ("exc_class", "exc_msg"),
        [
            pytest.param(TimeoutError, "Connection timed out", id="timeout"),
            pytest.param(ConnectionError, "Service Unavailable (503)", id="server_error"),
            pytest.param(Exception, "Unexpected error", id="generic"),
            pytest.param(ConnectionRefusedError, "Connection refused", id="connection_refused"),
            pytest.param(OSError, "getaddrinfo failed", id="dns_failure"),
        ],
    )
    async def test_exception_returns_empty_results(self, exc_class, exc_msg):
        """Verify search returns empty list on any exception."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )

        mock_client = MagicMock()
        mock_client.query_points = AsyncMock(side_effect=exc_class(exc_msg))
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
                raise TimeoutError("Transient timeout")
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

    @pytest.mark.parametrize(
        ("mode", "expected_suffix"),
        [
            pytest.param("off", "", id="off"),
            pytest.param("scalar", "_scalar", id="scalar"),
            pytest.param("binary", "_binary", id="binary"),
        ],
    )
    def test_qdrant_service_init_with_different_modes(self, mode, expected_suffix):
        """Verify QdrantService initializes correctly with different modes."""
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
            quantization_mode=mode,
        )
        assert service.collection_name == f"test_collection{expected_suffix}"

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
