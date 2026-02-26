"""Smoke test: apartments collection has data and search works."""

import os

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue


QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "apartments"


@pytest.fixture
def qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION", ""),
    reason="RUN_INTEGRATION not set",
)
class TestApartmentsIngestion:
    def test_collection_has_points(self, qdrant: QdrantClient) -> None:
        info = qdrant.get_collection(COLLECTION)
        assert info.points_count >= 297

    def test_scroll_with_filter(self, qdrant: QdrantClient) -> None:
        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(must=[FieldCondition(key="rooms", match=MatchValue(value=2))]),
            limit=5,
            with_payload=True,
        )
        assert len(results) > 0
        for point in results:
            assert point.payload["rooms"] == 2

    def test_point_has_all_vectors(self, qdrant: QdrantClient) -> None:
        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            limit=1,
            with_vectors=True,
        )
        assert len(results) == 1
        vectors = results[0].vector
        assert "dense" in vectors
        assert "bm42" in vectors
