"""Fixtures for baseline tests."""

import os
from datetime import UTC, datetime, timedelta

import pytest

from .collector import LangfuseMetricsCollector
from .manager import BaselineManager


@pytest.fixture
def langfuse_collector():
    """Create Langfuse metrics collector."""
    return LangfuseMetricsCollector(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )


@pytest.fixture
def baseline_manager(langfuse_collector):
    """Create baseline manager."""
    return BaselineManager(collector=langfuse_collector)


@pytest.fixture
def test_time_range():
    """Default time range for tests (last hour)."""
    now = datetime.now(UTC)
    return {
        "from_ts": now - timedelta(hours=1),
        "to_ts": now,
    }
