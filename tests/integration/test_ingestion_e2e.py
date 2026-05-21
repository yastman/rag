"""E2E test for CocoIndex ingestion pipeline (requires Docker services).

Milestone J: Document Ingestion Pipeline (2026-02-02)

Run with: RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_ingestion_e2e.py -v
"""

import os
import uuid
from contextlib import suppress
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests disabled (set RUN_INTEGRATION_TESTS=1)",
)


@pytest.fixture
def sample_markdown_content() -> bytes:
    """Sample markdown content for testing."""
    return b"""# Test Document

## Introduction

This is a test document for the ingestion pipeline.
It contains multiple sections to test chunking.

## Section One

Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

## Section Two

Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.

## Conclusion

This concludes the test document.
"""


@pytest.fixture
def e2e_collection_name() -> str:
    """Use a separate collection for tests."""
    return f"test_ingestion_e2e_{uuid.uuid4().hex[:8]}"


async def _delete_test_collection(collection_name: str) -> None:
    """Best-effort cleanup for Qdrant collections created by these tests."""
    from telegram_bot.services.ingestion_cocoindex import CocoIndexIngestionService

    service = CocoIndexIngestionService(collection_name=collection_name)
    try:
        with suppress(Exception):
            client = service.qdrant_client
            if client.collection_exists(collection_name):
                client.delete_collection(collection_name)
    finally:
        await service.close()


async def _seed_ingestion_collection(tmp_path: Path, collection_name: str) -> str:
    """Create a populated test collection before asserting success-path stats."""
    from telegram_bot.services.ingestion_cocoindex import CocoIndexIngestionService

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "seed_doc.md").write_text("# Seed\n\nContent for ingestion status checks.")

    service = CocoIndexIngestionService(collection_name=collection_name)
    try:
        stats = await service.ingest_directory(seed_dir)
        assert stats.total_documents >= 1
        assert stats.errors == []

        collection_stats = await service.get_collection_stats()
        assert "error" not in collection_stats
        assert collection_stats.get("points_count", 0) > 0
        return collection_name
    finally:
        await service.close()


@pytest.fixture
async def seeded_ingestion_collection(tmp_path: Path, e2e_collection_name: str) -> str:
    """Yield a collection that has known ingestion data."""
    try:
        yield await _seed_ingestion_collection(tmp_path, e2e_collection_name)
    finally:
        await _delete_test_collection(e2e_collection_name)


class TestIngestionServiceE2E:
    """E2E tests for CocoIndexIngestionService."""

    async def test_ingest_directory_creates_nodes(self, tmp_path: Path, e2e_collection_name: str):
        """Test that directory ingestion creates nodes in Qdrant."""
        from telegram_bot.services.ingestion_cocoindex import CocoIndexIngestionService

        # Create test file
        test_file = tmp_path / "test_doc.md"
        test_file.write_text("# Test\n\nThis is test content for ingestion.")

        service = CocoIndexIngestionService(collection_name=e2e_collection_name)

        try:
            # Ingest directory
            stats = await service.ingest_directory(tmp_path)

            assert stats.total_documents >= 1
            assert stats.errors == []

            # Verify collection has points (#1629 — success path must require
            # actual data, not a no-op).
            collection_stats = await service.get_collection_stats()
            assert "error" not in collection_stats
            assert collection_stats.get("points_count", 0) > 0

        finally:
            await _delete_test_collection(e2e_collection_name)
            await service.close()

    async def test_get_collection_stats(self, seeded_ingestion_collection: str):
        """Test getting collection statistics."""
        from telegram_bot.services.ingestion_cocoindex import CocoIndexIngestionService

        service = CocoIndexIngestionService(collection_name=seeded_ingestion_collection)

        try:
            stats = await service.get_collection_stats()

            # Success path: stats must describe a healthy collection. Graceful
            # failures are covered by the dedicated negative test
            # test_ingest_gdrive_without_credentials_fails_gracefully (#1629).
            assert isinstance(stats, dict)
            assert "error" not in stats
            assert "name" in stats

        finally:
            await service.close()

    async def test_ingest_gdrive_without_credentials_fails_gracefully(self):
        """Test that GDrive ingestion fails gracefully without credentials."""
        from telegram_bot.services.ingestion_cocoindex import CocoIndexIngestionService

        service = CocoIndexIngestionService()
        service.google_service_account_key = None

        try:
            stats = await service.ingest_gdrive("fake_folder_id")

            assert len(stats.errors) >= 1
            assert "GOOGLE_SERVICE_ACCOUNT_KEY" in stats.errors[0]

        finally:
            await service.close()


class TestQdrantSetupScript:
    """Tests for setup_ingestion_collection.py script."""

    def test_script_imports(self):
        """Test that setup script can be imported."""
        from scripts.setup_ingestion_collection import (
            COLLECTION_NAME,
            VECTOR_SIZE,
            get_client,
            setup_collection,
        )

        assert COLLECTION_NAME == "documents"
        assert VECTOR_SIZE == 1024
        assert callable(get_client)
        assert callable(setup_collection)

    def test_get_client_uses_env_vars(self, monkeypatch):
        """Test that get_client respects environment variables."""
        monkeypatch.setenv("QDRANT_URL", "http://test:6333")

        from scripts.setup_ingestion_collection import get_client

        client = get_client()
        # Client should be created (connection test requires live service)
        assert client is not None


class TestConvenienceFunctionsE2E:
    """E2E tests for convenience functions."""

    async def test_get_ingestion_status(self, seeded_ingestion_collection: str):
        """Test get_ingestion_status convenience function."""
        from telegram_bot.services.ingestion_cocoindex import get_ingestion_status

        status = await get_ingestion_status(seeded_ingestion_collection)

        # Success path: status must describe a healthy collection (#1629).
        assert isinstance(status, dict)
        assert "error" not in status
        assert "name" in status
