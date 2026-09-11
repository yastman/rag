"""Shared pytest fixtures for all tests."""

import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# Register shared URL/collection fixtures (issue #2066). Smoke and integration
# tiers consume `redis_url`, `qdrant_url`, `qdrant_api_key`,
# `qdrant_collection`, `bge_m3_url`, `openai_api_key` from a single source.
pytest_plugins = ["tests.fixtures.config"]


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

# Repository .env is never loaded in test processes (#3447): tests must not
# inherit ambient credentials or endpoints (Redis/Qdrant/BGE URLs, API keys).
# Setting this also blocks any later in-process dotenv loads (e.g. bot
# config bootstrap) for the rest of the pytest run.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def pytest_configure(config) -> None:
    """Pin one harness run id per invocation (#3414).

    Set in the controller process so pytest-xdist workers (spawned after
    configure) inherit the SAME run id; the canonical `make e2e-harness`
    entry exports E2E_RUN_ID explicitly, which wins via setdefault.
    """
    os.environ.setdefault("E2E_RUN_ID", uuid.uuid4().hex[:12])


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply stable directory-based markers for test tiering."""
    root = Path(__file__).resolve().parent
    path_to_marker = {
        root / "unit": "unit",
        root / "integration": "integration",
        root / "smoke": "smoke",
        root / "e2e": "e2e",
        root / "chaos": "chaos",
        root / "load": "load",
        root / "contract": "contract",
        root / "baseline": "baseline",
    }

    for item in items:
        item_path = Path(str(item.path)).resolve()
        for directory, marker in path_to_marker.items():
            if directory in item_path.parents:
                item.add_marker(getattr(pytest.mark, marker))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    """Required-mode hook (#3414): service lanes never skip to green.

    When ``E2E_HARNESS_REQUIRED=1`` (legacy ``E2E_CORE_STRICT=1``), a test
    marked ``requires_services`` that ends up SKIPPED is reported as FAILED
    with its skip reason — a required capability can never become green
    solely through ``pytest.skip``.
    """
    outcome = yield
    report = outcome.get_result()
    if not report.skipped:
        return
    if item.get_closest_marker("requires_services") is None:
        return
    from tests.e2e_core.live_harness import required_mode

    if required_mode():
        reason = report.longrepr or "service-required test skipped"
        report.longrepr = (
            f"REQUIRED MODE (#3414): zero service-related skips allowed; this "
            f"requires_services test skipped: {reason}"
        )
        report.outcome = "failed"


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
