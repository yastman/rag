"""Shared pytest fixtures for all tests."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from dotenv import load_dotenv


# Load environment variables before any imports
load_dotenv()


# =============================================================================
# HTTP MOCKING FIXTURES
# =============================================================================


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for HTTP tests."""
    with patch("httpx.AsyncClient") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx.Response."""

    def _create(status_code=200, json_data=None, text=""):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=response
            )
        return response

    return _create


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_context_chunks():
    """Sample context chunks for LLM tests."""
    return [
        {
            "text": "Квартира в Солнечном берегу, 2 комнаты, 65 м².",
            "metadata": {"title": "Апартамент у моря", "city": "Солнечный берег", "price": 75000},
            "score": 0.92,
        },
        {
            "text": "Студия в Несебре, первая линия, 35 м².",
            "metadata": {"title": "Студия на первой линии", "city": "Несебр", "price": 45000},
            "score": 0.87,
        },
    ]


@pytest.fixture(scope="session")
def qdrant_url():
    """Qdrant server URL."""
    return os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.fixture(scope="session")
def qdrant_api_key():
    """Qdrant API key (optional)."""
    return os.getenv("QDRANT_API_KEY", "")


@pytest.fixture(scope="session")
def qdrant_collection():
    """Qdrant collection name for tests."""
    return os.getenv("QDRANT_COLLECTION", "test_documents")


@pytest.fixture(scope="session")
def redis_url():
    """Redis server URL."""
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="session")
def bge_m3_url():
    """BGE-M3 embedding service URL."""
    return os.getenv("BGE_M3_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def openai_api_key():
    """OpenAI API key for LLM tests."""
    return os.getenv("OPENAI_API_KEY", "")


@pytest.fixture
def sample_texts():
    """Sample texts for embedding tests."""
    return [
        "Кримінальний кодекс України визначає злочини та покарання.",
        "Стаття 115 передбачає відповідальність за умисне вбивство.",
        "Крадіжка є таємним викраденням чужого майна.",
    ]


@pytest.fixture
def sample_query():
    """Sample query for search tests."""
    return "Яке покарання за крадіжку?"
