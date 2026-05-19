# tests/integration/conftest.py
"""Integration test configuration."""

import os

import pytest


# ---------------------------------------------------------------------------
# TEST_SERVICES_HOST: allows running integration tests against a remote host
# when Docker daemon is on a MacBook or another machine (issue #1552).
# Usage: TEST_SERVICES_HOST=192.168.x.x pytest tests/integration/
# Default: "localhost" (works when Docker ports are local)
# ---------------------------------------------------------------------------
TEST_SERVICES_HOST = os.getenv("TEST_SERVICES_HOST", "localhost")


@pytest.fixture(scope="session")
def services_host() -> str:
    """Return the host where Docker services are listening.

    Override via TEST_SERVICES_HOST env var when services run on a remote
    machine (e.g. Docker daemon on MacBook with ``ssh -L`` tunnel or no
    tunnel configured).
    """
    return TEST_SERVICES_HOST
