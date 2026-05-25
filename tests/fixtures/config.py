"""Shared configuration fixtures (URLs, API keys)."""

import os

import pytest


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
    """Qdrant collection name for tests.

    Defaults to the production contract value ``gdrive_documents_bge``
    (matches ``telegram_bot/config.py`` and ``compose.yml``) so smoke
    tests run against the same collection naming the bot uses
    end-to-end. Override per-environment via ``QDRANT_COLLECTION``.
    """
    return os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge")


@pytest.fixture(scope="session")
def redis_url():
    """Redis server URL with password support."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in url:
        url = url.replace("redis://", f"redis://:{password}@", 1)
    return url


@pytest.fixture(scope="session")
def bge_m3_url():
    """BGE-M3 embedding service URL."""
    return os.getenv("BGE_M3_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def openai_api_key():
    """OpenAI API key for LLM tests."""
    return os.getenv("OPENAI_API_KEY", "")
