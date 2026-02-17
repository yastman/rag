"""Docker service connectivity tests.

Each test gracefully skips if the target service is not available.
Run with `make docker-up` or `make docker-full-up` first.
"""

import pytest
import redis.asyncio as aioredis
from qdrant_client import QdrantClient
from redis.exceptions import AuthenticationError as RedisAuthError


asyncpg = pytest.importorskip("asyncpg", reason="asyncpg not installed")


def _check_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (OSError, TimeoutError):
            return False


@pytest.mark.asyncio
async def test_postgres_connection():
    """Test PostgreSQL connectivity."""
    if not _check_tcp("localhost", 5432):
        pytest.skip("PostgreSQL not running on localhost:5432")

    conn = await asyncpg.connect(
        user="postgres", password="postgres", database="postgres", host="localhost", port=5432
    )
    version = await conn.fetchval("SELECT version()")
    await conn.close()
    assert "PostgreSQL" in version


@pytest.mark.asyncio
async def test_redis_connection():
    """Test Redis connectivity."""
    if not _check_tcp("localhost", 6379):
        pytest.skip("Redis not running on localhost:6379")

    import os

    password = os.getenv("REDIS_PASSWORD", "")
    url = f"redis://:{password}@localhost:6379" if password else "redis://localhost:6379"
    r = aioredis.from_url(url)
    try:
        assert await r.ping() is True
    except RedisAuthError:
        pytest.skip("Redis requires authentication (set REDIS_PASSWORD)")
    finally:
        await r.aclose()


def test_qdrant_health():
    """Test Qdrant connectivity."""
    if not _check_tcp("localhost", 6333):
        pytest.skip("Qdrant not running on localhost:6333")

    client = QdrantClient(url="http://localhost:6333", timeout=5)
    collections = client.get_collections()
    assert collections is not None


@pytest.mark.asyncio
async def test_bge_m3_health():
    """Test BGE-M3 embedding service health."""
    if not _check_tcp("localhost", 8000):
        pytest.skip("BGE-M3 not running on localhost:8000")

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8000/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_lightrag_health():
    """Test LightRAG service health."""
    if not _check_tcp("localhost", 9621):
        pytest.skip("LightRAG not running on localhost:9621")

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:9621/health") as resp:
            assert resp.status == 200


@pytest.mark.asyncio
async def test_mlflow_health():
    """Test MLflow tracking server health."""
    if not _check_tcp("localhost", 5000):
        pytest.skip("MLflow not running on localhost:5000")

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:5000/health") as resp:
            assert resp.status == 200


@pytest.mark.asyncio
async def test_docling_health():
    """Test Docling document parsing service health."""
    if not _check_tcp("localhost", 5001):
        pytest.skip("Docling not running on localhost:5001")

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:5001/health") as resp:
            assert resp.status == 200
