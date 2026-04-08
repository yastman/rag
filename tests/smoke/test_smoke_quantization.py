# tests/smoke/test_smoke_quantization.py
"""Smoke tests for Qdrant quantization A/B testing."""

import os
import socket
import time

import numpy as np
import pytest


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture
async def voyage_service():
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY not set")
    try:
        from telegram_bot.services.voyage import VoyageService
    except Exception as exc:  # pragma: no cover - depends on optional third-party packages
        pytest.skip(f"Voyage stack unavailable in this environment: {exc}")

    return VoyageService(api_key=api_key)


@pytest.fixture
async def qdrant_service():
    from telegram_bot.services.qdrant import QdrantService

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge")

    service = QdrantService(url=url, api_key=api_key or None, collection_name=collection)
    yield service
    await service.close()


@pytest.mark.skipif(not _is_port_open("localhost", 6333), reason="Qdrant not running (6333)")
class TestSmokeQuantization:
    """Test quantization A/B switching."""

    async def test_search_with_quantization_returns_results(self, voyage_service, qdrant_service):
        """Search with quantization should return results."""
        embedding = await voyage_service.embed_query("квартира в Солнечном берегу")
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding,
            quantization_ignore=False,
            top_k=5,
        )
        assert len(results) > 0

    async def test_search_without_quantization_returns_results(
        self, voyage_service, qdrant_service
    ):
        """Search without quantization should return results."""
        embedding = await voyage_service.embed_query("квартира в Солнечном берегу")
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding,
            quantization_ignore=True,
            top_k=5,
        )
        assert len(results) > 0

    async def test_quantization_results_overlap_60_percent(self, voyage_service, qdrant_service):
        """Results should have >= 60% overlap between modes."""
        embedding = await voyage_service.embed_query("студия с видом на море")

        results_with = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding, quantization_ignore=False, top_k=5
        )
        results_without = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding, quantization_ignore=True, top_k=5
        )

        ids_with = {r["id"] for r in results_with}
        ids_without = {r["id"] for r in results_without}

        overlap = len(ids_with & ids_without) / max(len(ids_with), 1)
        assert overlap >= 0.6, f"Overlap {overlap:.0%} < 60%"

    @pytest.mark.xfail(reason="Flaky timing comparison — depends on system load", strict=False)
    async def test_quantization_latency_comparison(self, voyage_service, qdrant_service):
        """Measure latency with/without quantization (5 runs each, compare p95)."""
        embedding = await voyage_service.embed_query("апартаменты с бассейном")

        # Warmup
        await qdrant_service.hybrid_search_rrf(dense_vector=embedding, top_k=3)

        # Measure with quantization
        times_with = []
        for _ in range(5):
            start = time.time()
            await qdrant_service.hybrid_search_rrf(
                dense_vector=embedding, quantization_ignore=False, top_k=5
            )
            times_with.append((time.time() - start) * 1000)

        # Measure without quantization
        times_without = []
        for _ in range(5):
            start = time.time()
            await qdrant_service.hybrid_search_rrf(
                dense_vector=embedding, quantization_ignore=True, top_k=5
            )
            times_without.append((time.time() - start) * 1000)

        p95_with = np.percentile(times_with, 95)
        p95_without = np.percentile(times_without, 95)

        # Log results (informational)
        print(f"\nQuantization p95: {p95_with:.0f}ms (with) vs {p95_without:.0f}ms (without)")

        # Quantization should not be significantly slower (allow 10x margin for CI/dev)
        assert p95_with <= p95_without * 10, (
            f"Quantization too slow: {p95_with:.0f}ms vs {p95_without:.0f}ms"
        )
