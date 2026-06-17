# tests/smoke/test_zoo_smoke.py
"""Zoo smoke tests - verify all services are alive and functional."""

import os
import socket

import pytest


pytestmark = pytest.mark.requires_services


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _redis_url_candidates() -> list[str]:
    """Return Redis URLs to try in order (auth first, then plain)."""
    base_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    if "@" in base_url:
        return [base_url]

    urls: list[str] = []
    for password in (os.getenv("REDIS_PASSWORD", ""), "dev_redis_pass"):
        if password:
            auth_url = base_url.replace("redis://", f"redis://:{password}@", 1)
            if auth_url not in urls:
                urls.append(auth_url)
    if base_url not in urls:
        urls.append(base_url)
    return urls


class TestZooHealth:
    """Health checks for services without existing coverage."""

    def test_litellm_sdk_router_contract(self):
        """The local smoke contract uses the in-process LiteLLM SDK router."""
        from src.runtime.llm.router import DEFAULT_MODEL_ALIAS, build_model_list

        aliases = {entry["model_name"] for entry in build_model_list()}
        assert DEFAULT_MODEL_ALIAS in aliases
        assert "gpt-4o-mini" in aliases
