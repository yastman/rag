"""Unit tests for Qdrant E2E preflight."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.e2e.qdrant_preflight import (
    CollectionRequirement,
    _vector_names_from_info,
    run_qdrant_preflight,
)


def _make_info(points_count: int, vector_names: list[str], sparse_names: list[str] | None = None):
    """Build a mock collection info object."""
    info = MagicMock()
    info.points_count = points_count
    info.config.params.vectors = {name: MagicMock() for name in vector_names}
    if sparse_names:
        info.config.params.sparse_vectors = {name: MagicMock() for name in sparse_names}
    else:
        info.config.params.sparse_vectors = {}
    return info


class TestRunQdrantPreflight:
    def test_missing_gdrive_documents_bge_fails_with_sanitized_remediation(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = False

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert not result.ok
        assert "gdrive_documents_bge" in result.message
        assert "does not exist" in result.message
        assert any(
            item["collection"] == "gdrive_documents_bge" and item["exists"] is False
            for item in result.checked
        )

    def test_below_minimum_count_fails(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True
            mock_client.get_collection.return_value = _make_info(
                points_count=0, vector_names=["dense", "colbert"]
            )

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert not result.ok
        assert "has 0 points" in result.message
        assert "minimum required: 1" in result.message

    def test_missing_dense_vector_fails(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True
            mock_client.get_collection.return_value = _make_info(
                points_count=5, vector_names=["colbert"]
            )

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert not result.ok
        assert "missing required vectors" in result.message
        assert "dense" in result.message

    def test_missing_colbert_vector_fails(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True
            mock_client.get_collection.return_value = _make_info(
                points_count=5, vector_names=["dense"]
            )

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert not result.ok
        assert "missing required vectors" in result.message
        assert "colbert" in result.message

    def test_apartments_below_minimum_count_fails(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True
            mock_client.get_collection.return_value = _make_info(
                points_count=0, vector_names=["dense", "colbert"]
            )

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="apartments",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert not result.ok
        assert "apartments" in result.message
        assert "has 0 points" in result.message

    def test_no_payload_contents_printed(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True
            info = _make_info(points_count=5, vector_names=["dense", "colbert"])
            # Attach a payload schema that must NOT leak into output
            info.config.params.payload_schema = {"secret_field": "secret_value"}
            mock_client.get_collection.return_value = info

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert result.ok
        assert "secret" not in result.message.lower()
        assert "payload" not in result.message.lower()
        for item in result.checked:
            assert "payload" not in item
            assert "secret" not in str(item).lower()

    def test_passes_when_all_requirements_met(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True
            mock_client.get_collection.return_value = _make_info(
                points_count=10, vector_names=["dense", "colbert"]
            )

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert result.ok
        assert result.message == "Qdrant preflight passed"
        assert result.checked[0]["points_count"] == 10
        assert result.checked[0]["vectors"] == ["dense", "colbert"]

    def test_multiple_requirements_partial_failure(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.side_effect = [True, False]
            mock_client.get_collection.return_value = _make_info(
                points_count=10, vector_names=["dense", "colbert"]
            )

            result = run_qdrant_preflight(
                qdrant_url="http://localhost:6333",
                requirements=(
                    CollectionRequirement(
                        name="gdrive_documents_bge",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                    CollectionRequirement(
                        name="apartments",
                        min_points=1,
                        required_vectors=frozenset(["dense", "colbert"]),
                    ),
                ),
            )

        assert not result.ok
        assert "apartments" in result.message
        assert "does not exist" in result.message
        assert len(result.checked) == 2

    def test_connection_failure_returns_early(self):
        with patch("scripts.e2e.qdrant_preflight.QdrantClient") as MockClient:
            MockClient.side_effect = Exception("Connection refused")

            result = run_qdrant_preflight(
                qdrant_url="http://bad-host:6333",
                requirements=(),
            )

        assert not result.ok
        assert "Connection refused" in result.message
        assert result.checked == []


class TestVectorNamesFromInfo:
    def test_extracts_named_vectors(self):
        info = MagicMock()
        info.config.params.vectors = {"dense": MagicMock(), "colbert": MagicMock()}
        info.config.params.sparse_vectors = {"bm42": MagicMock()}
        assert sorted(_vector_names_from_info(info)) == ["bm42", "colbert", "dense"]

    def test_handles_single_vector_config(self):
        class SingleVec:
            vector_name = "default"

        info = MagicMock()
        info.config.params.vectors = SingleVec()
        info.config.params.sparse_vectors = {}
        assert _vector_names_from_info(info) == ["default"]

    def test_handles_none_vectors(self):
        info = MagicMock()
        info.config.params.vectors = None
        info.config.params.sparse_vectors = None
        assert _vector_names_from_info(info) == []
