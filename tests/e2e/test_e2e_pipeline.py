"""E2E pipeline tests - full query to answer flow.

Tests the complete pipeline from query to answer using real services.
Requires running Docker services and API keys.
"""

import os
import time

import pytest


pytestmark = pytest.mark.legacy_api

try:
    from telegram_bot.services import (
        CacheService,
        LLMService,
        QueryPreprocessor,
        RetrieverService,
        VoyageService,
    )
except ImportError:
    pytest.skip("Legacy imports removed in LangGraph migration", allow_module_level=True)


def skip_if_missing_keys():
    """Check if required API keys are present."""
    voyage_key = os.getenv("VOYAGE_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not voyage_key or not openai_key:
        pytest.skip("VOYAGE_API_KEY and OPENAI_API_KEY required for E2E tests")


@pytest.fixture(scope="module")
def preprocessor():
    """Create preprocessor instance."""
    return QueryPreprocessor()


@pytest.fixture(scope="module")
def voyage_service():
    """Create Voyage service for embeddings and reranking (requires VOYAGE_API_KEY)."""
    skip_if_missing_keys()
    return VoyageService(api_key=os.getenv("VOYAGE_API_KEY", ""))


@pytest.fixture(scope="module")
def embedder(voyage_service):
    """Create embedding service (requires VOYAGE_API_KEY)."""
    return voyage_service


@pytest.fixture(scope="module")
def reranker(voyage_service):
    """Create reranker service (requires VOYAGE_API_KEY)."""
    return voyage_service


@pytest.fixture(scope="module")
def retriever():
    """Create hybrid retriever (requires Qdrant)."""
    return RetrieverService(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY", ""),
        collection_name="contextual_bulgaria_voyage",
    )


@pytest.fixture(scope="module")
def llm():
    """Create LLM service (requires OPENAI_API_KEY)."""
    skip_if_missing_keys()
    return LLMService(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
    )


@pytest.fixture(scope="module")
async def cache_service():
    """Create cache service (requires Redis)."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    service = CacheService(redis_url=redis_url, distance_threshold=0.15)
    await service.initialize()
    yield service
    await service.close()


class TestE2EPipelinePreprocessor:
    """Preprocessor E2E tests (no external dependencies)."""

    def test_analyze_returns_all_fields(self, preprocessor):
        """analyze() returns complete result dict."""
        result = preprocessor.analyze("Sunny Beach корпус 5")

        assert "original_query" in result
        assert "normalized_query" in result
        assert "rrf_weights" in result
        assert "cache_threshold" in result
        assert "is_exact" in result

    def test_translit_works(self, preprocessor):
        """Transliteration converts Latin to Cyrillic."""
        result = preprocessor.analyze("Sunny Beach apartments")

        assert "Солнечный берег" in result["normalized_query"]
        assert "Sunny Beach" not in result["normalized_query"]

    def test_exact_query_detection(self, preprocessor):
        """Exact queries (ID, корпус) get sparse-favored weights."""
        result = preprocessor.analyze("квартира ID 12345")

        assert result["is_exact"] is True
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["cache_threshold"] == 0.05


class TestE2EPipelineEmbedding:
    """Embedding E2E tests (requires VOYAGE_API_KEY)."""

    async def test_embed_query_returns_vector(self, embedder):
        """embed_query returns 1024-dim vector."""
        vector = await embedder.embed_query("тестовый запрос")

        assert isinstance(vector, list)
        assert len(vector) == 1024
        assert all(isinstance(v, float) for v in vector)

    async def test_embed_documents_batches_correctly(self, embedder):
        """embed_documents handles multiple documents."""
        docs = ["документ один", "документ два", "документ три"]
        vectors = await embedder.embed_documents(docs)

        assert len(vectors) == 3
        assert all(len(v) == 1024 for v in vectors)


class TestE2EPipelineRetrieval:
    """Retrieval E2E tests (requires Qdrant + VOYAGE_API_KEY)."""

    async def test_hybrid_search_returns_results(self, embedder, retriever):
        """Hybrid search returns results from Qdrant."""
        if not retriever._is_healthy:
            pytest.skip("Qdrant not available")

        query = "квартиры в Солнечном береге"
        embedding = await embedder.embed_query(query)

        # Hybrid search with dense-only (sparse vectors indexed at ingestion time)
        results = retriever.hybrid_search(
            dense_vector=embedding,
            sparse_indices=[],  # No runtime sparse for now
            sparse_values=[],
            rrf_weights=(0.6, 0.4),
            top_k=5,
        )

        assert len(results) > 0
        assert "text" in results[0]
        assert "metadata" in results[0]
        assert "score" in results[0]

    async def test_translit_query_finds_results(self, embedder, retriever, preprocessor):
        """Query with Latin names works via translit."""
        if not retriever._is_healthy:
            pytest.skip("Qdrant not available")

        # Preprocess to convert Latin to Cyrillic
        analysis = preprocessor.analyze("Sunny Beach apartments")
        assert "Солнечный берег" in analysis["normalized_query"]

        embedding = await embedder.embed_query(analysis["normalized_query"])
        results = retriever.hybrid_search(
            dense_vector=embedding,
            sparse_indices=[],
            sparse_values=[],
            top_k=5,
        )

        assert len(results) > 0


class TestE2EPipelineReranking:
    """Reranking E2E tests (requires VOYAGE_API_KEY)."""

    async def test_reranker_scores_documents(self, reranker):
        """Reranker assigns relevance scores."""
        query = "квартира у моря"
        documents = [
            {"text": "Апартаменты с видом на море в Бургасе", "metadata": {}},
            {"text": "Офисное здание в центре города", "metadata": {}},
            {"text": "Квартира на первой линии пляжа", "metadata": {}},
        ]

        reranked = await reranker.rerank(query, documents, top_k=3)

        assert len(reranked) == 3
        assert all("rerank_score" in r for r in reranked)
        # Top result should be about sea/beach
        assert "море" in reranked[0]["text"] or "пляж" in reranked[0]["text"]


class TestE2EPipelineLLM:
    """LLM E2E tests (requires OPENAI_API_KEY)."""

    async def test_generate_answer_returns_text(self, llm):
        """generate_answer returns non-empty answer."""
        chunks = [
            {
                "text": "Квартира в Солнечном берегу, 50 кв.м, 2 комнаты, цена 45000 евро",
                "metadata": {"title": "Апартамент 101", "city": "Солнечный берег"},
                "score": 0.95,
            }
        ]

        answer = await llm.generate_answer("Есть ли квартиры до 50000 евро?", chunks)

        assert isinstance(answer, str)
        assert len(answer) > 20


class TestE2EPipelineCache:
    """Cache E2E tests (requires Redis + VOYAGE_API_KEY)."""

    async def test_semantic_cache_store_and_retrieve(self, cache_service):
        """Semantic cache stores and retrieves answers."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized (no VOYAGE_API_KEY)")

        # Unique query to avoid test pollution
        query = f"тестовый E2E запрос {time.time()}"
        answer = "тестовый E2E ответ для кэша"

        # Store
        await cache_service.store_semantic_cache(query, answer)

        # Retrieve
        cached = await cache_service.check_semantic_cache(query)

        assert cached is not None
        assert "E2E ответ" in cached

    async def test_cache_miss_returns_none(self, cache_service):
        """Non-existent query returns None."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Query that definitely doesn't exist
        cached = await cache_service.check_semantic_cache(f"несуществующий запрос {time.time()}")

        assert cached is None


class TestE2EFullPipeline:
    """Full pipeline E2E tests (all services)."""

    async def test_complete_query_to_answer_flow(
        self, preprocessor, embedder, retriever, reranker, llm
    ):
        """Complete flow: preprocess -> embed -> retrieve -> rerank -> generate."""
        if not retriever._is_healthy:
            pytest.skip("Qdrant not available")

        # 1. Preprocess
        query = "apartments in Sunny Beach near the sea"
        analysis = preprocessor.analyze(query)
        assert "Солнечный берег" in analysis["normalized_query"]

        # 2. Embed
        embedding = await embedder.embed_query(analysis["normalized_query"])
        assert len(embedding) == 1024

        # 3. Retrieve
        results = retriever.hybrid_search(
            dense_vector=embedding,
            sparse_indices=[],
            sparse_values=[],
            rrf_weights=(
                analysis["rrf_weights"]["dense"],
                analysis["rrf_weights"]["sparse"],
            ),
            top_k=10,
        )
        assert len(results) > 0

        # 4. Rerank (if enough results)
        if len(results) >= 3:
            reranked = await reranker.rerank(
                analysis["normalized_query"],
                results,
                top_k=5,
            )
            assert len(reranked) > 0
            final_results = reranked
        else:
            final_results = results

        # 5. Generate answer
        answer = await llm.generate_answer(query, final_results[:5])
        assert len(answer) > 50
