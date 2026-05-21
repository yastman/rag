"""Shared pytest fixtures for all tests."""

import logging
import os
from pathlib import Path

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
        root / "benchmark": "benchmark",
        root / "contract": "contract",
        root / "baseline": "baseline",
    }

    for item in items:
        item_path = Path(str(item.path)).resolve()
        for directory, marker in path_to_marker.items():
            if directory in item_path.parents:
                item.add_marker(getattr(pytest.mark, marker))
