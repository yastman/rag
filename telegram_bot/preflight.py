"""Bot dependency preflight checks."""

import logging

import httpx
import redis.asyncio as aioredis

from .config import BotConfig


logger = logging.getLogger(__name__)


async def check_dependencies(config: BotConfig) -> dict[str, bool]:
    """Check all bot dependencies are reachable. Returns status dict."""
    results: dict[str, bool] = {}
    timeout = httpx.Timeout(5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Redis
        try:
            r = aioredis.from_url(config.redis_url)
            await r.ping()
            await r.aclose()
            results["redis"] = True
        except Exception as e:
            logger.error("Preflight FAIL: Redis — %s", e)
            results["redis"] = False

        # Qdrant collection
        try:
            collection = config.qdrant_collection
            resp = await client.get(f"{config.qdrant_url}/collections/{collection}")
            results["qdrant"] = resp.status_code == 200
            if not results["qdrant"]:
                logger.error("Preflight FAIL: Qdrant collection — %s", resp.status_code)
        except Exception as e:
            logger.error("Preflight FAIL: Qdrant — %s", e)
            results["qdrant"] = False

        # BGE-M3 embedding service
        try:
            resp = await client.get(f"{config.bge_m3_url}/health")
            results["bge_m3"] = resp.status_code == 200
            if not results["bge_m3"]:
                logger.error("Preflight FAIL: BGE-M3 — %s", resp.status_code)
        except Exception as e:
            logger.error("Preflight FAIL: BGE-M3 — %s", e)
            results["bge_m3"] = False

        # LiteLLM proxy
        try:
            resp = await client.get(f"{config.llm_base_url}/health")
            results["litellm"] = resp.status_code == 200
            if not results["litellm"]:
                logger.error("Preflight FAIL: LiteLLM — %s", resp.status_code)
        except Exception as e:
            logger.error("Preflight FAIL: LiteLLM — %s", e)
            results["litellm"] = False

    return results
