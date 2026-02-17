"""Shared pytest fixtures for all tests."""

import logging
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from dotenv import load_dotenv


# Set testing flag to prevent heavy imports in src/__init__.py
os.environ["RAG_TESTING"] = "true"

# Disable Langfuse tracing by default for tests to avoid timeouts when Langfuse
# is not running locally. Opt-in in Makefile targets that require tracing.
os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")

# Disable all OpenTelemetry exporters to prevent network calls in unit tests
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")

# Disable Langfuse completely (belt and suspenders)
os.environ.setdefault("LANGFUSE_ENABLED", "false")
os.environ.setdefault("LANGFUSE_HOST", "http://localhost:3001")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

# Ragas registers an atexit shutdown hook that logs debug messages late in
# interpreter teardown. In pytest this can hit already-closed handlers and print
# noisy "I/O operation on closed file" tracebacks after all tests passed.
for _logger_name in ("ragas", "ragas._analytics"):
    _logger = logging.getLogger(_logger_name)
    _logger.disabled = True
    _logger.propagate = False

# Load environment variables before any imports
load_dotenv()


# =============================================================================
# MOCK HEAVY IMPORTS FOR UNIT TESTS
# =============================================================================
# These modules are slow to import due to model loading.  Mocks are installed
# in ``pytest_configure`` (earliest hook, before collection) and removed in
# ``pytest_unconfigure`` so that no MagicMock leaks into sys.modules after the
# session ends.
#
# Policy: NEVER assign to sys.modules at module level.  Use
# ``monkeypatch.setitem(sys.modules, ...)`` inside fixtures, or register mocks
# via ``pytest_configure`` for collection-time needs.  See
# ``.claude/rules/testing.md`` § "sys.modules hygiene".

_saved_modules: dict[str, object] = {}
_mocked_module_names: list[str] = []


def pytest_configure(config):
    """Install lightweight mocks for heavy ML libs before test collection."""
    # -- sentence_transformers / FlagEmbedding (slow model loading) ----------
    # Skip if: (a) real module already loaded, or (b) re-entry (already mocked).
    _already_mocked = "sentence_transformers" in _mocked_module_names
    _real_module_loaded = "sentence_transformers" in sys.modules and not isinstance(
        sys.modules["sentence_transformers"], MagicMock
    )
    if not _already_mocked and not _real_module_loaded:
        for mod_name in ("sentence_transformers", "FlagEmbedding"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)

        mock_st = MagicMock()
        mock_st.CrossEncoder = MagicMock()
        mock_st.SentenceTransformer = MagicMock()
        sys.modules["sentence_transformers"] = mock_st
        _mocked_module_names.append("sentence_transformers")

        mock_flag = MagicMock()
        mock_flag.BGEM3FlagModel = MagicMock()
        sys.modules["FlagEmbedding"] = mock_flag
        _mocked_module_names.append("FlagEmbedding")

    # -- aiogram (optional Telegram runtime dep) -----------------------------
    try:
        import importlib.util

        if importlib.util.find_spec("aiogram") is None:
            raise ModuleNotFoundError("aiogram not installed")
    except ModuleNotFoundError:
        for mod_name in ("aiogram", "aiogram.filters", "aiogram.types"):
            _saved_modules[mod_name] = sys.modules.get(mod_name)

        mock_aiogram = MagicMock()
        mock_aiogram.Bot = MagicMock()
        mock_aiogram.Dispatcher = MagicMock()
        mock_aiogram.F = MagicMock()

        mock_filters = MagicMock()
        mock_filters.Command = MagicMock()

        mock_types = MagicMock()
        mock_types.Message = MagicMock()

        sys.modules["aiogram"] = mock_aiogram
        sys.modules["aiogram.filters"] = mock_filters
        sys.modules["aiogram.types"] = mock_types
        _mocked_module_names.extend(["aiogram", "aiogram.filters", "aiogram.types"])


def pytest_unconfigure(config):
    """Restore original modules after test session."""
    for mod_name in _mocked_module_names:
        original = _saved_modules.get(mod_name)
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original  # type: ignore[assignment]
    _mocked_module_names.clear()
    _saved_modules.clear()


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


@pytest.fixture(scope="session")
def sample_context_chunks():
    """Sample context chunks for LLM tests (read-only, session-scoped)."""
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


@pytest.fixture(scope="session")
def sample_texts():
    """Sample texts for embedding tests (read-only, session-scoped)."""
    return [
        "Кримінальний кодекс України визначає злочини та покарання.",
        "Стаття 115 передбачає відповідальність за умисне вбивство.",
        "Крадіжка є таємним викраденням чужого майна.",
    ]


@pytest.fixture(scope="session")
def sample_query():
    """Sample query for search tests (read-only, session-scoped)."""
    return "Яке покарання за крадіжку?"
