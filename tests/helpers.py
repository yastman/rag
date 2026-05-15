"""Shared helpers for all test tiers."""

import os


def get_services_host() -> str:
    """Return the host for service connectivity checks.

    Defaults to ``localhost``. Set ``TEST_SERVICES_HOST`` to point to a
    remote Docker host when the Docker daemon is not local.
    """
    return os.getenv("TEST_SERVICES_HOST", "localhost")
