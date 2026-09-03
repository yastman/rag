# tests/integration/test_unified_ingestion_e2e.py
"""E2E: Markdown-only unified ingestion against live Qdrant + BGE-M3 (#3244, #3235).

One bounded scenario proving the supported production path end-to-end:
only ``.md`` files are indexed, payloads carry the deterministic identity
fields, an unchanged second pass is an idempotent skip, and a changed file
atomically replaces its prior chunks. Non-Markdown files are ignored.

Requires live Qdrant + BGE-M3; both are probed and the test skips (not
fails) when they are unreachable.
"""

import contextlib
import os

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_services,
    pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests",
    ),
]


def _qdrant_reachable(url: str) -> bool:
    import httpx

    try:
        return httpx.get(f"{url}/collections", timeout=2).status_code == 200
    except Exception:
        return False


def _bge_reachable(url: str) -> bool:
    import httpx

    try:
        return (
            httpx.post(f"{url}/encode/dense", json={"texts": ["ping"]}, timeout=5).status_code
            == 200
        )
    except Exception:
        return False


@pytest.fixture
def temp_sync_dir(tmp_path):
    """Create temporary sync directory: two .md files and one ignored .txt."""
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()

    (sync_dir / "alpha.md").write_text(
        "# Alpha\n\nFirst document body.\n\n## Section\n\nMore content here.\n",
        encoding="utf-8",
    )
    (sync_dir / "beta.md").write_text(
        "# Beta\n\nSecond document body.\n",
        encoding="utf-8",
    )
    # Non-Markdown files are outside the supported contract; must be ignored.
    (sync_dir / "ignored.txt").write_text("not ingested", encoding="utf-8")

    return sync_dir


@pytest.fixture
def test_collection_name():
    """Unique collection name for test isolation."""
    return os.getenv("UNIFIED_E2E_COLLECTION", "test_unified_e2e")


@pytest.fixture
def qdrant_url():
    return os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.fixture
def bge_url():
    return os.getenv("BGE_M3_URL", "http://localhost:8000")


@pytest.fixture
def qdrant_client(qdrant_url):
    """Get Qdrant client."""
    from qdrant_client import QdrantClient

    return QdrantClient(url=qdrant_url, timeout=30)


@pytest.fixture
def cleanup_collection(qdrant_client, test_collection_name):
    """Clean up test collection after test."""
    yield
    with contextlib.suppress(Exception):
        qdrant_client.delete_collection(test_collection_name)


@pytest.fixture
def e2e_config(temp_sync_dir, test_collection_name, qdrant_url, bge_url):
    from src.ingestion.unified.config import UnifiedConfig

    return UnifiedConfig(
        sync_dir=temp_sync_dir,
        manifest_dir=temp_sync_dir,
        collection_name=test_collection_name,
        qdrant_url=qdrant_url,
        bge_m3_url=bge_url,
    )


async def _bootstrap_collection(e2e_config) -> None:
    """Create the collection via the real bootstrap command."""
    import argparse

    from src.ingestion.unified.commands import cmd_bootstrap

    args = argparse.Namespace(command="bootstrap", require_colbert=False)
    with _patch_config(e2e_config):
        exit_code = await cmd_bootstrap(args)
    assert exit_code == 0, "bootstrap failed"


def _patch_config(e2e_config):
    from unittest.mock import patch

    return patch("src.ingestion.unified.config.UnifiedConfig", return_value=e2e_config)


def _sources_payloads(qdrant_client, collection_name: str) -> list[dict]:
    """Return payload dicts for every point in the collection."""
    payloads: list[dict] = []
    offset = None
    while True:
        records, offset = qdrant_client.scroll(
            collection_name=collection_name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for record in records:
            if record.payload:
                payloads.append(dict(record.payload))
        if offset is None:
            return payloads


async def test_markdown_only_ingestion_e2e(
    temp_sync_dir,
    e2e_config,
    qdrant_client,
    test_collection_name,
    qdrant_url,
    bge_url,
    cleanup_collection,
) -> None:
    """Markdown files index; .txt is ignored; unchanged skips; changed replaces."""
    from src.ingestion.unified.flow import run_once

    if not (_qdrant_reachable(qdrant_url) and _bge_reachable(bge_url)):
        pytest.skip(f"Qdrant ({qdrant_url}) or BGE-M3 ({bge_url}) not reachable")

    await _bootstrap_collection(e2e_config)

    # --- Pass 1: only the two .md files are processed -------------------
    first = run_once(e2e_config)
    assert first.processed == 2, f"expected 2 .md processed, got {first}"
    assert first.errors == 0, f"unexpected errors: {first.error_details}"

    payloads = _sources_payloads(qdrant_client, test_collection_name)
    sources = {p.get("metadata", {}).get("source") for p in payloads}
    assert sources == {"alpha.md", "beta.md"}, f"unexpected indexed sources: {sources}"
    for payload in payloads:
        metadata = payload["metadata"]
        assert metadata.get("file_id"), "payload must carry file_id"
        assert metadata.get("content_hash"), "payload must carry content_hash"
        # Writer contract: source_type is inferred from the source path
        # (Markdown files classify as "file" — unchanged writer behavior).
        assert metadata.get("source_type") == "file"
    assert len(payloads) >= 3, "expected the sectioned document to yield multiple chunks"

    alpha_hashes = {
        p["metadata"]["content_hash"] for p in payloads if p["metadata"]["source"] == "alpha.md"
    }
    assert len(alpha_hashes) == 1, "all chunks of one version share one content_hash"

    # --- Pass 2: unchanged files are an idempotent skip ------------------
    second = run_once(e2e_config)
    assert second.processed == 0, f"unchanged files must not re-index, got {second}"
    assert second.skipped == 2
    assert second.errors == 0

    # --- Pass 3: changed file atomically replaces its chunks -------------
    (temp_sync_dir / "alpha.md").write_text(
        "# Alpha\n\nRewritten body with entirely new content.\n",
        encoding="utf-8",
    )
    third = run_once(e2e_config)
    assert third.processed == 1, f"only the changed file may re-index, got {third}"
    assert third.errors == 0

    payloads_after = _sources_payloads(qdrant_client, test_collection_name)
    alpha_payloads = [
        p for p in payloads_after if p.get("metadata", {}).get("source") == "alpha.md"
    ]
    new_hashes = {p["metadata"]["content_hash"] for p in alpha_payloads}
    assert new_hashes.isdisjoint(alpha_hashes), "old alpha.md content must be swept"
    assert "Rewritten body with entirely new content." in "\n".join(
        p.get("page_content", "") for p in alpha_payloads
    ), "new alpha.md chunks must be searchable in the collection"
