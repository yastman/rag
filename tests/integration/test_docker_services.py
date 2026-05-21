"""Docker service connectivity tests.

Each test gracefully skips if the target service is not available.
Run with `make docker-up` or `make docker-full-up` first.
"""

import os

import pytest
import redis.asyncio as aioredis
from qdrant_client import QdrantClient
from redis.exceptions import AuthenticationError as RedisAuthError


asyncpg = pytest.importorskip("asyncpg", reason="asyncpg not installed")

SERVICES_HOST = os.environ.get("TEST_SERVICES_HOST", "localhost")


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
    if not _check_tcp(SERVICES_HOST, 5432):
        pytest.skip(f"PostgreSQL not running on {SERVICES_HOST}:5432")

    conn = await asyncpg.connect(
        user="postgres", password="postgres", database="postgres", host=SERVICES_HOST, port=5432
    )
    version = await conn.fetchval("SELECT version()")
    await conn.close()
    assert "PostgreSQL" in version


@pytest.mark.asyncio
async def test_redis_connection():
    """Test Redis connectivity."""
    if not _check_tcp(SERVICES_HOST, 6379):
        pytest.skip(f"Redis not running on {SERVICES_HOST}:6379")

    import os

    password = os.getenv("REDIS_PASSWORD", "")
    url = f"redis://:{password}@{SERVICES_HOST}:6379" if password else f"redis://{SERVICES_HOST}:6379"
    r = aioredis.from_url(url)
    try:
        assert await r.ping() is True
    except RedisAuthError:
        pytest.skip("Redis requires authentication (set REDIS_PASSWORD)")
    finally:
        await r.aclose()


def test_qdrant_health():
    """Test Qdrant connectivity."""
    if not _check_tcp(SERVICES_HOST, 6333):
        pytest.skip(f"Qdrant not running on {SERVICES_HOST}:6333")

    client = QdrantClient(url=f"http://{SERVICES_HOST}:6333", timeout=5)
    collections = client.get_collections()
    assert collections is not None


@pytest.mark.asyncio
async def test_bge_m3_health():
    """Test BGE-M3 embedding service health."""
    if not _check_tcp(SERVICES_HOST, 8000):
        pytest.skip(f"BGE-M3 not running on {SERVICES_HOST}:8000")

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://{SERVICES_HOST}:8000/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_docling_health():
    """Test Docling document parsing service health."""
    if not _check_tcp(SERVICES_HOST, 5001):
        pytest.skip(f"Docling not running on {SERVICES_HOST}:5001")

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://{SERVICES_HOST}:5001/health") as resp:
            assert resp.status == 200
