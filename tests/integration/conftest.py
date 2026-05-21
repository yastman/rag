# tests/integration/conftest.py
"""Integration test configuration."""

import os

SERVICES_HOST = os.environ.get("TEST_SERVICES_HOST", "localhost")
