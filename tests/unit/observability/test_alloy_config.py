"""Tests for Grafana Alloy configuration file."""

from pathlib import Path

import pytest


ALLOY_CONFIG_PATH = Path("docker/monitoring/alloy.alloy")


@pytest.fixture()
def alloy_config() -> str:
    """Read the Alloy configuration file."""
    return ALLOY_CONFIG_PATH.read_text()


def test_alloy_config_file_exists() -> None:
    """Assert docker/monitoring/alloy.alloy exists."""
    assert ALLOY_CONFIG_PATH.exists(), f"Alloy config not found at {ALLOY_CONFIG_PATH}"


def test_alloy_config_has_docker_discovery(alloy_config: str) -> None:
    """Assert config contains discovery.docker component."""
    assert "discovery.docker" in alloy_config


def test_alloy_config_has_loki_source(alloy_config: str) -> None:
    """Assert config contains loki.source.docker component."""
    assert "loki.source.docker" in alloy_config


def test_alloy_config_forwards_to_loki(alloy_config: str) -> None:
    """Assert config references the Loki endpoint."""
    assert "loki:3100" in alloy_config
