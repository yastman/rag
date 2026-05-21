"""Fixtures for baseline tests."""

import os

import pytest

from .collector import LangfuseMetricsCollector


@pytest.fixture
def langfuse_collector():
    """Create Langfuse metrics collector."""
    return LangfuseMetricsCollector(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )
