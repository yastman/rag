"""Shared fixtures for the observability test module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml


CONTRACT_PATH = Path(__file__).resolve().parent / "trace_contract.yaml"

# Voice-agent service identity constants
VOICE_AGENT_SERVICE_NAME = "voice-agent"
VOICE_SESSION_TRACE_NAME = "voice-session"
VOICE_TRACE_TAGS = ["voice", "call-lifecycle"]


@pytest.fixture(scope="session")
def trace_contract() -> dict:
    """Load the canonical trace contract YAML."""
    with open(CONTRACT_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def required_families(trace_contract: dict) -> list[str]:
    """Required trace family names from contract."""
    return trace_contract["required_families"]


@pytest.fixture()
def mock_langfuse_client() -> MagicMock:
    """Provide a mocked Langfuse client with common API structure."""
    client = MagicMock()
    client.auth_check.return_value = True
    client.api = MagicMock()
    client.api.trace = MagicMock()
    client.api.trace.list.return_value = MagicMock(data=[])
    client.api.trace.get.return_value = MagicMock()
    client.flush.return_value = None
    return client
