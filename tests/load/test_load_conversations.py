# tests/load/test_load_conversations.py
"""Load tests for parallel chat conversations."""

import json
import os
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.legacy_api

try:
    from telegram_bot.services.query_router import (
        QueryType,
        classify_query,
        get_chitchat_response,
    )
except ImportError:
    pytest.skip("Legacy imports removed in LangGraph migration", allow_module_level=True)

from tests.load.chat_simulator import run_parallel_chats
from tests.load.metrics_collector import (
    LoadMetrics,
    analyze_metrics,
    format_report,
    load_baseline,
    save_baseline,
)


BASELINE_PATH = Path(__file__).parent / "baseline.json"
REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def use_mocks() -> bool:
    return os.getenv("LOAD_USE_MOCKS", "0") == "1"


@pytest.fixture
def load_config():
    return {
        "chat_count": int(os.getenv("LOAD_CHAT_COUNT", "10")),
        "duration_min": int(os.getenv("LOAD_DURATION_MIN", "2")),
        "use_mocks": use_mocks(),
    }


@pytest.fixture
async def services(load_config):
    if load_config["use_mocks"]:
        from unittest.mock import AsyncMock

        voyage = AsyncMock()
        voyage.embed_query = AsyncMock(return_value=[0.1] * 1024)

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(
            return_value=[
                {"id": "1", "score": 0.9, "text": "Mock", "metadata": {}},
            ]
        )
        qdrant.close = AsyncMock()

        # Track stored queries to simulate cache hits
        stored_queries: set = set()

        async def mock_get_cached(query_hash: str):
            if query_hash in stored_queries:
                return [{"id": "1", "score": 0.9, "text": "Cached", "metadata": {}}]
            return None

        async def mock_store(query_hash: str, results):
            stored_queries.add(query_hash)

        cache = AsyncMock()
        cache.get_cached_search = AsyncMock(side_effect=mock_get_cached)
        cache.store_search_results = AsyncMock(side_effect=mock_store)
        cache.close = AsyncMock()

        yield {"voyage": voyage, "qdrant": qdrant, "cache": cache}
    else:
        from telegram_bot.services.cache import CacheService

        from telegram_bot.services.qdrant import QdrantService
        from telegram_bot.services.voyage import VoyageService

        voyage_key = os.getenv("VOYAGE_API_KEY")
        if not voyage_key:
            pytest.skip("VOYAGE_API_KEY not set")

        voyage = VoyageService(api_key=voyage_key)
        qdrant = QdrantService(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
            collection_name=os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4"),
        )
        cache = CacheService(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"))
        await cache.initialize()

        yield {"voyage": voyage, "qdrant": qdrant, "cache": cache}

        await qdrant.close()
        await cache.close()


class TestLoadConversations:
    """Load tests for parallel chat conversations."""
    async def test_parallel_chats(self, load_config, services, request):
        """Run parallel chats and verify p95 thresholds."""
        metrics = LoadMetrics()
        chat_count = load_config["chat_count"]

        async def process_message(query: str, chat_id: int) -> float:
            start = time.time()

            # Routing
            route_start = time.time()
            query_type = classify_query(query)
            metrics.record_routing((time.time() - route_start) * 1000)

            if query_type == QueryType.CHITCHAT:
                _ = get_chitchat_response(query)
                latency = (time.time() - start) * 1000
                metrics.record_full_rag(latency)
                return latency

            try:
                cache_start = time.time()
                cached = await services["cache"].get_cached_search(
                    query_hash=str(hash(query))[:16],
                )

                if cached:
                    metrics.record_cache_hit((time.time() - cache_start) * 1000)
                    latency = (time.time() - start) * 1000
                    metrics.record_full_rag(latency)
                    return latency
                metrics.record_cache_miss()

                embedding = await services["voyage"].embed_query(query)

                qdrant_start = time.time()
                results = await services["qdrant"].hybrid_search_rrf(
                    dense_vector=embedding, top_k=5
                )
                metrics.record_qdrant((time.time() - qdrant_start) * 1000)

                await services["cache"].store_search_results(
                    query_hash=str(hash(query))[:16], results=results
                )

            except Exception:
                metrics.record_error()
                raise

            latency = (time.time() - start) * 1000
            metrics.record_full_rag(latency)
            return latency

        start_time = time.time()
        await run_parallel_chats(
            chat_count=chat_count,
            process_message=process_message,
            stagger_start_sec=0.2,
        )
        duration = time.time() - start_time

        baseline = load_baseline(BASELINE_PATH)
        result = analyze_metrics(metrics, baseline, require_ttft=False)

        report = format_report(result, metrics, duration, chat_count)
        print(f"\n{report}")

        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "load_summary.json"
        with open(report_path, "w") as f:
            json.dump(
                {
                    "routing_p95": result.routing_p95,
                    "cache_hit_p95": result.cache_hit_p95,
                    "qdrant_p95": result.qdrant_p95,
                    "full_rag_p95": result.full_rag_p95,
                    "cache_hit_rate": result.cache_hit_rate,
                    "passed": result.passed,
                    "chat_count": chat_count,
                    "duration_sec": duration,
                },
                f,
                indent=2,
            )

        if request.config.getoption("--update-baseline", default=False):
            save_baseline(BASELINE_PATH, result)
            print(f"\nBaseline updated: {BASELINE_PATH}")

        assert result.passed, f"Load test failed: {result.failures}"


def pytest_addoption(parser):
    parser.addoption("--update-baseline", action="store_true", default=False)
