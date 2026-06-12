# tests/smoke/test_zoo_smoke.py
"""Zoo smoke tests - verify all services are alive and functional."""

import os
import socket

import httpx
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

    @pytest.fixture
    def user_base_url(self):
        return os.getenv("USER_BASE_URL", "http://localhost:8003")

    @pytest.mark.skipif(
        not _is_port_open("localhost", 8003), reason="user-base not running (port 8003)"
    )
    @pytest.mark.asyncio
    async def test_user_base_health(self, user_base_url):
        """user-base /health returns status=healthy."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{user_base_url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") in ("ok", "healthy"), (
                f"Expected status 'ok' or 'healthy', got: {data.get('status')}"
            )

    @pytest.mark.skipif(
        not _is_port_open("localhost", 8003), reason="user-base not running (port 8003)"
    )
    @pytest.mark.asyncio
    async def test_user_base_embed_returns_768_dim(self, user_base_url):
        """user-base /embed returns 768-dimensional vector."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{user_base_url}/embed", json={"text": "тестовый запрос"})
            assert response.status_code == 200
            data = response.json()
            embedding = data.get("embedding", [])
            assert len(embedding) == 768, f"Expected 768 dims, got {len(embedding)}"

    def test_litellm_sdk_router_contract(self):
        """The local smoke contract uses the in-process LiteLLM SDK router."""
        from src.runtime.llm.router import DEFAULT_MODEL_ALIAS, build_model_list

        aliases = {entry["model_name"] for entry in build_model_list()}
        assert DEFAULT_MODEL_ALIAS in aliases
        assert "gpt-4o-mini" in aliases
