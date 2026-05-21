"""Conftest for ingestion unit tests.

Mocks heavy ML dependencies (fastembed) before test collection.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


_MOCKED_MODULES: list[str] = []


def pytest_configure(config: object) -> None:
    """Mock unavailable heavy ML deps before test collection."""
    if "fastembed" not in sys.modules:
        mock_fastembed = MagicMock()
        mock_fastembed.SparseTextEmbedding = MagicMock()
        sys.modules["fastembed"] = mock_fastembed
        _MOCKED_MODULES.append("fastembed")


def pytest_unconfigure(config: object) -> None:
    """Clean up mocked modules after tests."""
    for mod in _MOCKED_MODULES:
        sys.modules.pop(mod, None)
    _MOCKED_MODULES.clear()


@pytest.fixture
def mock_qdrant_client():
    """Mock sync QdrantClient."""
    client = MagicMock()
    client.count.return_value = MagicMock(count=0)
    client.delete = MagicMock()
    client.upsert = MagicMock()
    ***REMOVED*** Default: no orphan points exist for the file_id, so the post-upsert
    ***REMOVED*** stale-id sweep finds nothing to delete (***REMOVED***1602 atomic-replace).
    client.scroll.return_value = ([], None)
    return client


@pytest.fixture
def mock_bge_client():
    """Mock BGEM3SyncClient for sparse/dense/colbert embeddings."""
    client = MagicMock()
    client.encode_sparse.return_value = MagicMock(
        weights=[{"indices": [1, 2], "values": [0.5, 0.3]}]
    )
    client.encode_colbert.return_value = MagicMock(colbert_vecs=[[[0.1] * 128] * 5])
    client.encode_dense.return_value = MagicMock(vectors=[[0.2] * 1024])
    return client


@pytest.fixture
def mock_voyage():
    """Mock VoyageService client (Voyage API path)."""
    voyage = MagicMock()
    voyage._client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
    voyage._model_docs = "voyage-4-large"
    return voyage


@pytest.fixture
def writer_voyage(mock_qdrant_client, mock_bge_client, mock_voyage):
    """QdrantHybridWriter using Voyage for dense embeddings."""
    with (
        patch(
            "src.ingestion.unified.qdrant_writer.QdrantClient",
            return_value=mock_qdrant_client,
        ),
        patch(
            "telegram_bot.services.bge_m3_client.BGEM3SyncClient",
            return_value=mock_bge_client,
        ),
        patch(
            "telegram_bot.services.VoyageService",
            return_value=mock_voyage,
        ),
    ):
        w = QdrantHybridWriter(
            qdrant_url="http://localhost:6333",
            voyage_api_key="test_key",
            use_local_embeddings=False,
        )
    ***REMOVED*** After construction, inject mocks so tests can set side_effects.
    w.client = mock_qdrant_client
    w._bge_client = mock_bge_client
    w.voyage = mock_voyage
    yield w


@pytest.fixture
def writer_local(mock_qdrant_client, mock_bge_client):
    """QdrantHybridWriter using local BGE-M3 for all embeddings."""
    with (
        patch(
            "src.ingestion.unified.qdrant_writer.QdrantClient",
            return_value=mock_qdrant_client,
        ),
        patch(
            "telegram_bot.services.bge_m3_client.BGEM3SyncClient",
            return_value=mock_bge_client,
        ),
    ):
        w = QdrantHybridWriter(
            qdrant_url="http://localhost:6333",
            use_local_embeddings=True,
        )
    w.client = mock_qdrant_client
    w._bge_client = mock_bge_client
    yield w
