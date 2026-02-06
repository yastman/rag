"""Bot dependency preflight checks."""

import contextlib
import logging

import httpx
import redis.asyncio as aioredis

from .config import BotConfig


logger = logging.getLogger(__name__)

# Cache key prefixes used by CacheService (see telegram_bot/services/cache.py)
# Used for synthetic write/read/ttl/delete verification at startup.
CACHE_KEY_PREFIXES = [
    "sparse:",
    "analysis:",
    "search:",
    "rerank:",
    "conversation:",
]


async def _check_redis_deep(redis_url: str) -> tuple[bool, dict[str, str]]:
    """Deep Redis health check: PING, INFO, eviction policy, keyspace.

    Returns:
        Tuple of (passed, details_dict). ``passed`` is True only when all
        sub-checks succeed. ``details_dict`` always carries human-readable
        diagnostic strings.
    """
    details: dict[str, str] = {}
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        # 1. PING
        await r.ping()
        details["ping"] = "ok"

        # 2. INFO — memory / clients
        info_memory = await r.info("memory")
        info_clients = await r.info("clients")
        info_server = await r.info("server")

        used_mem = info_memory.get("used_memory_human", "?")
        max_policy = info_memory.get("maxmemory_policy", "unknown")
        connected = info_clients.get("connected_clients", "?")
        redis_version = info_server.get("redis_version", "?")

        details["used_memory_human"] = used_mem
        details["maxmemory_policy"] = max_policy
        details["connected_clients"] = str(connected)
        details["redis_version"] = redis_version

        logger.info(
            "Preflight Redis INFO: version=%s, memory=%s, policy=%s, clients=%s",
            redis_version,
            used_mem,
            max_policy,
            connected,
        )

        # 3. Eviction policy check
        if max_policy == "noeviction":
            logger.warning(
                "Preflight WARN: maxmemory_policy is 'noeviction' "
                "(recommended: volatile-lfu). OOM errors possible under load."
            )
            details["policy_warning"] = "noeviction detected — should be volatile-lfu"

        # 4. Keyspace — at least db0 should have keys
        info_keyspace = await r.info("keyspace")
        db0 = info_keyspace.get("db0")
        if db0:
            details["keyspace_db0"] = str(db0)
            logger.info("Preflight Redis keyspace db0: %s", db0)
        else:
            details["keyspace_db0"] = "empty"
            logger.warning("Preflight WARN: Redis db0 has no keys — cache is cold")

        return True, details

    except Exception as exc:
        details["error"] = str(exc)
        return False, details
    finally:
        await r.aclose()


async def _verify_cache_synthetic(redis_url: str) -> tuple[bool, list[str]]:
    """Synthetic write/read/TTL/delete for each cache key prefix.

    Creates a ``__preflight_test`` key per prefix, validates the full
    lifecycle, then removes it. Returns (all_passed, list_of_errors).
    """
    errors: list[str] = []
    r = aioredis.from_url(redis_url, decode_responses=True)
    test_ttl = 30  # seconds — short-lived test keys

    try:
        for prefix in CACHE_KEY_PREFIXES:
            test_key = f"{prefix}__preflight_test"
            test_value = "preflight_ok"

            try:
                # Write with TTL
                await r.setex(test_key, test_ttl, test_value)

                # Read back
                got = await r.get(test_key)
                if got != test_value:
                    errors.append(
                        f"{prefix} read-back mismatch: expected '{test_value}', got '{got}'"
                    )
                    continue

                # Check TTL is set
                remaining = await r.ttl(test_key)
                if remaining <= 0:
                    errors.append(f"{prefix} TTL not set (ttl={remaining})")
                    continue

                # Delete
                deleted = await r.delete(test_key)
                if deleted != 1:
                    errors.append(f"{prefix} delete returned {deleted} (expected 1)")
                    continue

                # Confirm deletion
                after = await r.get(test_key)
                if after is not None:
                    errors.append(f"{prefix} key still exists after delete")
                    continue

            except Exception as exc:
                errors.append(f"{prefix} error: {exc}")
                # Best-effort cleanup
                with contextlib.suppress(Exception):
                    await r.delete(test_key)

        if errors:
            for err in errors:
                logger.error("Preflight cache verify FAIL: %s", err)
        else:
            logger.info(
                "Preflight cache verify: all %d prefixes OK",
                len(CACHE_KEY_PREFIXES),
            )

        return len(errors) == 0, errors

    finally:
        await r.aclose()


async def check_dependencies(config: BotConfig) -> dict[str, bool]:
    """Check all bot dependencies are reachable. Returns status dict."""
    results: dict[str, bool] = {}
    timeout = httpx.Timeout(5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # ----- Redis deep check (REDIS-01) -----
        try:
            passed, details = await _check_redis_deep(config.redis_url)
            results["redis"] = passed
            if not passed:
                logger.error("Preflight FAIL: Redis deep check — %s", details)
        except Exception as e:
            logger.error("Preflight FAIL: Redis — %s", e)
            results["redis"] = False

        # ----- Redis synthetic cache verification (REDIS-02) -----
        if results.get("redis"):
            try:
                cache_ok, cache_errors = await _verify_cache_synthetic(config.redis_url)
                results["redis_cache"] = cache_ok
                if not cache_ok:
                    logger.error(
                        "Preflight FAIL: Redis cache verify — %s",
                        cache_errors,
                    )
            except Exception as e:
                logger.error("Preflight FAIL: Redis cache verify — %s", e)
                results["redis_cache"] = False
        else:
            # Skip cache verification when Redis itself is down
            results["redis_cache"] = False
            logger.warning("Preflight SKIP: Redis cache verify (Redis unreachable)")

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

        # LiteLLM proxy (/health/liveliness doesn't require auth)
        try:
            resp = await client.get(f"{config.llm_base_url}/health/liveliness")
            results["litellm"] = resp.status_code == 200
            if not results["litellm"]:
                logger.error("Preflight FAIL: LiteLLM — %s", resp.status_code)
        except Exception as e:
            logger.error("Preflight FAIL: LiteLLM — %s", e)
            results["litellm"] = False

    return results
