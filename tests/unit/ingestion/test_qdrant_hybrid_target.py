"""Unit tests for src/ingestion/unified/targets/qdrant_hybrid_target.py.

Skipped entirely if cocoindex is not installed (ingest extra).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


cocoindex = pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")

from src.ingestion.unified.targets.qdrant_hybrid_target import (
    QdrantHybridTargetConnector,
    QdrantHybridTargetSpec,
    QdrantHybridTargetValues,
    compute_content_hash,
)


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    def test_returns_16_char_hex(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        result = compute_content_hash(f)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        assert compute_content_hash(f) == compute_content_hash(f)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert compute_content_hash(f1) != compute_content_hash(f2)

    def test_matches_sha256_first_16_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"test data")
        hasher = hashlib.sha256()
        hasher.update(b"test data")
        expected = hasher.hexdigest()[:16]
        assert compute_content_hash(f) == expected

    def test_large_file(self, tmp_path: Path) -> None:
        f = tmp_path / "large.bin"
        f.write_bytes(b"x" * 100_000)
        result = compute_content_hash(f)
        assert len(result) == 16


# ---------------------------------------------------------------------------
# QdrantHybridTargetSpec
# ---------------------------------------------------------------------------


class TestQdrantHybridTargetSpec:
    def test_default_qdrant_url(self) -> None:
        spec = QdrantHybridTargetSpec()
        assert spec.qdrant_url == "http://localhost:6333"

    def test_default_collection_name(self) -> None:
        spec = QdrantHybridTargetSpec()
        assert spec.collection_name == "gdrive_documents_bge"

    def test_default_max_tokens(self) -> None:
        spec = QdrantHybridTargetSpec()
        assert spec.max_tokens_per_chunk == 512

    def test_default_pipeline_version(self) -> None:
        spec = QdrantHybridTargetSpec()
        assert spec.pipeline_version == "v3.2.1"

    def test_from_config(self) -> None:
        from src.ingestion.unified.config import UnifiedConfig

        config = UnifiedConfig()
        spec = QdrantHybridTargetSpec.from_config(config)
        assert spec.qdrant_url == config.qdrant_url
        assert spec.collection_name == config.collection_name

    def test_custom_values(self) -> None:
        spec = QdrantHybridTargetSpec(
            qdrant_url="http://custom:6333",
            collection_name="my_col",
        )
        assert spec.qdrant_url == "http://custom:6333"
        assert spec.collection_name == "my_col"


# ---------------------------------------------------------------------------
# QdrantHybridTargetValues
# ---------------------------------------------------------------------------


class TestQdrantHybridTargetValues:
    def test_creates_correctly(self) -> None:
        val = QdrantHybridTargetValues(
            abs_path="/tmp/file.pdf",
            source_path="docs/file.pdf",
            file_name="file.pdf",
            mime_type="application/pdf",
            file_size=12345,
        )
        assert val.abs_path == "/tmp/file.pdf"
        assert val.file_size == 12345


# ---------------------------------------------------------------------------
# Connector static methods
# ---------------------------------------------------------------------------


class TestConnectorStatics:
    def test_get_persistent_key_format(self) -> None:
        spec = QdrantHybridTargetSpec(
            qdrant_url="http://localhost:6333",
            collection_name="my_col",
        )
        key = QdrantHybridTargetConnector.get_persistent_key(spec, "target")
        assert key == "my_col@http://localhost:6333"

    def test_describe_returns_string(self) -> None:
        desc = QdrantHybridTargetConnector.describe("my_col@http://localhost:6333")
        assert isinstance(desc, str)
        assert "my_col" in desc

    def test_apply_setup_change_create(self) -> None:
        spec = QdrantHybridTargetSpec()
        # Should not raise
        QdrantHybridTargetConnector.apply_setup_change("key", None, spec)

    def test_prepare_returns_spec(self) -> None:
        spec = QdrantHybridTargetSpec()
        result = QdrantHybridTargetConnector.prepare(spec)
        assert result is spec
