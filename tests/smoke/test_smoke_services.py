"""Smoke tests for all services health checks."""

import os
import socket

import httpx
import pytest
import redis.asyncio as redis
from redis.exceptions import AuthenticationError


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


class TestSmokeServices:
    """Verify all services are alive and responding."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _is_port_open("localhost", 6333), reason="Qdrant not running (6333)")
    async def test_qdrant_health(self):
        """Qdrant responds to health check."""
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/healthz")
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _is_port_open("localhost", 6379), reason="Redis not running (6379)")
    async def test_redis_health(self):
        """Redis responds to PING."""
        last_error: Exception | None = None
        for url in _redis_url_candidates():
            client = redis.from_url(url, socket_timeout=5.0)
            try:
                result = await client.ping()
                assert result is True
                await client.aclose()
                return
            except AuthenticationError as exc:
                last_error = exc
                await client.aclose()
                continue
            except Exception as exc:  # pragma: no cover - environment dependent
                last_error = exc
                await client.aclose()
                continue

        pytest.skip(f"Redis requires authentication (set REDIS_PASSWORD): {last_error}")

    @pytest.mark.skipif(
        not _is_port_open("localhost", 5000), reason="MLflow not running (port 5000)"
    )
    @pytest.mark.asyncio
    async def test_mlflow_health(self):
        """MLflow responds to health check."""
        url = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200

    @pytest.mark.skipif(
        not _is_port_open("localhost", 3001), reason="Langfuse not running (port 3001)"
    )
    @pytest.mark.asyncio
    async def test_langfuse_health(self):
        """Langfuse responds to health check."""
        url = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/public/health")
            assert response.status_code == 200

    @pytest.mark.skipif(
        not _is_port_open("localhost", 5001), reason="Docling not running (port 5001)"
    )
    @pytest.mark.asyncio
    async def test_docling_health(self):
        """Docling responds to health check."""
        url = os.getenv("DOCLING_URL", "http://localhost:5001")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200

    @pytest.mark.skipif(
        not _is_port_open("localhost", 9621), reason="LightRAG not running (port 9621)"
    )
    @pytest.mark.asyncio
    async def test_lightrag_health(self):
        """LightRAG responds to health check."""
        url = os.getenv("LIGHTRAG_URL", "http://localhost:9621")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_voyage_api_health(self):
        """Voyage API responds (minimal embed call)."""
        api_key = os.getenv("VOYAGE_API_KEY", "")
        if not api_key:
            pytest.skip("VOYAGE_API_KEY not set")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": ["test"], "model": "voyage-3-lite"},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_llm_api_health(self):
        """LLM API responds (minimal completion call)."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "")
        model = os.getenv("LLM_MODEL", "")

        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        # If custom model but no custom base_url, skip (misconfigured)
        if model and not model.startswith("gpt") and not base_url:
            pytest.skip(f"Custom model '{model}' requires OPENAI_BASE_URL")

        # Use defaults if not set
        if not base_url:
            base_url = "https://api.openai.com/v1"
        if not model:
            model = "gpt-4o-mini"

        # Skip if base_url points to a local service that isn't running
        if "localhost" in base_url or "127.0.0.1" in base_url:
            from urllib.parse import urlparse

            parsed = urlparse(base_url)
            port = parsed.port or 80
            if not _is_port_open(parsed.hostname or "localhost", port):
                pytest.skip(f"LLM API not running ({base_url})")

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                )
            except httpx.ConnectError:
                pytest.skip(f"LLM API not reachable ({base_url})")
            if response.status_code == 404:
                pytest.skip(f"LLM API endpoint not found ({base_url}/chat/completions)")
            assert response.status_code == 200
