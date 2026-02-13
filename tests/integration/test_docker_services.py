import aiohttp
import pytest
import redis.asyncio as redis
from qdrant_client import QdrantClient


asyncpg = pytest.importorskip("asyncpg", reason="asyncpg not installed")
async def test_postgres_connection():
    # Defaults from docker-compose
    conn = await asyncpg.connect(
        user="postgres", password="postgres", database="postgres", host="localhost", port=5432
    )
    version = await conn.fetchval("SELECT version()")
    await conn.close()
    assert "PostgreSQL" in version
async def test_redis_connection():
    r = redis.from_url("redis://localhost:6379")
    assert await r.ping() is True
    await r.close()


def test_qdrant_health():
    # Qdrant client uses sync HTTP by default or async
    client = QdrantClient(url="http://localhost:6333")
    collections = client.get_collections()
    assert collections is not None
async def test_bge_m3_health():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8000/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
async def test_lightrag_health():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:9621/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "healthy"
async def test_mlflow_health():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:5000/health") as resp:
            assert resp.status == 200
            text = await resp.text()
            assert "OK" in text or "healthy" in text
async def test_docling_health():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:5001/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
