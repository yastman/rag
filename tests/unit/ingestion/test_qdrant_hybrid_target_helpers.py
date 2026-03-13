"""Helper-level tests for qdrant_hybrid_target."""

from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.targets.qdrant_hybrid_target import (
    QdrantHybridTargetConnector,
    QdrantHybridTargetSpec,
    compute_content_hash,
)


def test_compute_content_hash_is_stable(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.txt"
    file_path.write_text("payload", encoding="utf-8")

    assert compute_content_hash(file_path) == compute_content_hash(file_path)


def test_target_spec_from_config_maps_core_fields() -> None:
    config = UnifiedConfig()
    spec = QdrantHybridTargetSpec.from_config(config)

    assert spec.collection_name == config.collection_name
    assert spec.qdrant_url == config.qdrant_url


def test_get_persistent_key_uses_collection_and_url() -> None:
    spec = QdrantHybridTargetSpec(collection_name="docs", qdrant_url="http://qdrant:6333")

    assert (
        QdrantHybridTargetConnector.get_persistent_key(spec, "ignored") == "docs@http://qdrant:6333"
    )
