# tests/smoke/test_smoke_quantization.py
"""Smoke tests for Qdrant quantization A/B testing.

Note: VoyageService-based quantization tests removed in P28 (voyageai dead-code deletion).
"""

import socket

import pytest


pytestmark = pytest.mark.requires_services


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture
async def qdrant_service():
    import os

    from src.runtime.services.qdrant import QdrantService

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge")

    service = QdrantService(url=url, api_key=api_key or None, collection_name=collection)
    yield service
    await service.close()
