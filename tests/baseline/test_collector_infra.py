"""Unit tests for infrastructure metrics collection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInfrastructureMetrics:
    """Tests for collect_infrastructure_metrics."""

    @pytest.fixture
    def collector(self):
        """Create LangfuseMetricsCollector with mocked deps."""
        from tests.baseline.collector import LangfuseMetricsCollector

        # Mock the Langfuse client to avoid initialization errors
        with patch("tests.baseline.collector.Langfuse"):
            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )
        collector.redis_url = "redis://localhost:6379"
        collector.qdrant_url = "http://localhost:6333"
        return collector

    async def test_collects_redis_stats(self, collector):
        """Should collect Redis INFO stats."""
        mock_info_stats = {
            "keyspace_hits": 1000,
            "keyspace_misses": 200,
            "evicted_keys": 5,
        }
        mock_info_memory = {
            "used_memory": 10 * 1024 * 1024,  # 10MB
            "used_memory_peak": 15 * 1024 * 1024,  # 15MB
            "maxmemory": 100 * 1024 * 1024,  # 100MB
        }

        with patch("redis.from_url") as mock_redis_from_url:
            mock_redis = MagicMock()
            mock_redis.info = MagicMock(side_effect=[mock_info_memory, mock_info_stats])
            mock_redis_from_url.return_value = mock_redis

            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = MagicMock()
                mock_response = MagicMock()
                mock_response.text = "qdrant_points_total 1000"
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock()

                metrics = await collector.collect_infrastructure_metrics()

        assert metrics["redis"]["keyspace_hits"] == 1000
        assert metrics["redis"]["hit_rate"] == 83.33  # 1000/(1000+200)*100

    async def test_collects_qdrant_metrics(self, collector):
        """Should fetch Qdrant /metrics endpoint."""
        with patch("redis.from_url") as mock_redis_from_url:
            mock_redis = MagicMock()
            mock_redis.info = MagicMock(return_value={})
            mock_redis_from_url.return_value = mock_redis

            mock_response = MagicMock()
            mock_response.text = "qdrant_points_total 1000\nqdrant_search_seconds_sum 5.0"

            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = MagicMock()
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock()

                metrics = await collector.collect_infrastructure_metrics()

        assert "qdrant_raw" in metrics or "qdrant" in metrics

    async def test_handles_redis_error(self, collector):
        """Should handle Redis connection errors gracefully."""
        with patch("redis.from_url") as mock_redis_from_url:
            mock_redis_from_url.side_effect = Exception("Connection refused")

            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = MagicMock()
                mock_response = MagicMock()
                mock_response.text = ""
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock()

                metrics = await collector.collect_infrastructure_metrics()

        assert "error" in metrics["redis"]

    async def test_handles_qdrant_error(self, collector):
        """Should handle Qdrant connection errors gracefully."""
        with patch("redis.from_url") as mock_redis_from_url:
            mock_redis = MagicMock()
            mock_redis.info = MagicMock(return_value={})
            mock_redis_from_url.return_value = mock_redis

            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = MagicMock()
                mock_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock()

                metrics = await collector.collect_infrastructure_metrics()

        assert "qdrant_error" in metrics

    async def test_includes_timestamp(self, collector):
        """Should include timestamp in metrics."""
        with patch("redis.from_url") as mock_redis_from_url:
            mock_redis = MagicMock()
            mock_redis.info = MagicMock(return_value={})
            mock_redis_from_url.return_value = mock_redis

            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = MagicMock()
                mock_response = MagicMock()
                mock_response.text = ""
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock()

                metrics = await collector.collect_infrastructure_metrics()

        assert "timestamp" in metrics
