"""Bot dependency preflight checks with CRITICAL/OPTIONAL classification."""

import contextlib
import logging
from enum import StrEnum
from urllib.parse import urlparse

import asyncpg
import httpx
import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient, models
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import BotConfig


logger = logging.getLogger(__name__)

# Retry settings for critical deps
CRITICAL_RETRIES = 3
CRITICAL_RETRY_DELAY = 5.0  # seconds
COLBERT_COVERAGE_WARN_THRESHOLD = 0.995

# Cache key prefixes used by CacheService (see telegram_bot/services/cache.py)
# Used for synthetic write/read/ttl/delete verification at startup.
CACHE_KEY_PREFIXES = [
    "sparse:",
    "analysis:",
    "search:",
    "rerank:",
    "conversation:",
]


class DepLevel(StrEnum):
    CRITICAL = "CRITICAL"
    OPTIONAL = "OPTIONAL"


# Dependency classification:
#   CRITICAL — bot cannot function, fail startup after retries
#   OPTIONAL — bot can degrade gracefully, warn and continue
DEP_CLASSIFICATION: dict[str, DepLevel] = {
    "redis": DepLevel.CRITICAL,
    "redis_cache": DepLevel.CRITICAL,
    "qdrant": DepLevel.CRITICAL,
    "bge_m3": DepLevel.CRITICAL,
    "postgres": DepLevel.OPTIONAL,
    "litellm": DepLevel.OPTIONAL,
    "langfuse": DepLevel.OPTIONAL,
}


class PreflightError(SystemExit):
    """Raised when a CRITICAL dependency is unreachable after retries."""

    def __init__(self, failed_deps: list[str]):
        self.failed_deps = failed_deps
        msg = (
            f"CRITICAL preflight failure — cannot start bot. "
            f"Unreachable after {CRITICAL_RETRIES} attempts: {', '.join(failed_deps)}"
        )
        super().__init__(msg)


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


async def _check_single_dep(
    name: str,
    config: BotConfig,
    client: httpx.AsyncClient,
) -> bool:
    """Run a single dependency check. Returns True if healthy."""
    if name == "redis":
        passed, details = await _check_redis_deep(config.redis_url)
        if not passed:
            logger.error("Preflight FAIL: Redis deep check — %s", details)
        return passed

    if name == "redis_cache":
        cache_ok, cache_errors = await _verify_cache_synthetic(config.redis_url)
        if not cache_ok:
            logger.error("Preflight FAIL: Redis cache verify — %s", cache_errors)
        return cache_ok

    if name == "qdrant":
        collection = config.qdrant_collection
        scheme = urlparse(config.qdrant_url).scheme.lower()
        effective_key = config.qdrant_api_key if scheme == "https" else None
        qdrant = AsyncQdrantClient(
            url=config.qdrant_url,
            api_key=effective_key,
            timeout=config.qdrant_timeout,
            prefer_grpc=True,
        )
        try:
            info = await qdrant.get_collection(collection)
            logger.info(
                "Preflight Qdrant: collection=%s, points=%s",
                collection,
                info.points_count,
            )

            # Validate expected vector configs (#570)
            dense_vectors = info.config.params.vectors
            sparse_vectors = info.config.params.sparse_vectors or {}
            dense_names = set(dense_vectors.keys()) if isinstance(dense_vectors, dict) else set()
            sparse_names = set(sparse_vectors.keys()) if isinstance(sparse_vectors, dict) else set()

            missing_required: set[str] = set()
            if "dense" not in dense_names:
                missing_required.add("dense")
            if "bm42" not in sparse_names:
                missing_required.add("bm42")
            if missing_required:
                logger.error(
                    "Preflight FAIL: Qdrant collection %s missing required vectors: %s",
                    collection,
                    sorted(missing_required),
                )
                return False

            if "colbert" not in dense_names:
                logger.warning(
                    "Preflight WARN: Qdrant collection %s missing 'colbert' vector "
                    "(server-side ColBERT reranking unavailable, RRF fallback active)",
                    collection,
                )
            elif info.points_count:
                try:
                    with_colbert = await qdrant.count(
                        collection_name=collection,
                        count_filter=models.Filter(
                            must=[models.HasVectorCondition(has_vector="colbert")]
                        ),
                        exact=True,
                    )
                    covered = int(with_colbert.count)
                    total = int(info.points_count)
                    ratio = covered / total

                    if ratio < COLBERT_COVERAGE_WARN_THRESHOLD:
                        logger.warning(
                            "Preflight WARN: Qdrant collection %s colbert coverage is %.2f%% "
                            "(%d/%d), below %.2f%% threshold",
                            collection,
                            ratio * 100,
                            covered,
                            total,
                            COLBERT_COVERAGE_WARN_THRESHOLD * 100,
                        )
                    else:
                        logger.info(
                            "Preflight Qdrant: colbert coverage %.2f%% (%d/%d)",
                            ratio * 100,
                            covered,
                            total,
                        )
                except Exception as exc:
                    logger.warning(
                        "Preflight WARN: Qdrant colbert coverage check failed: %s",
                        exc,
                    )

            return True
        except Exception as exc:
            logger.error("Preflight FAIL: Qdrant — %s", exc)
            return False
        finally:
            await qdrant.close()

    if name == "bge_m3":
        resp = await client.get(f"{config.bge_m3_url}/health")
        if resp.status_code != 200:
            logger.error("Preflight FAIL: BGE-M3 — %s", resp.status_code)
            return False
        # Warm encode to ensure model is loaded and warmed
        warmup_resp = await client.post(
            f"{config.bge_m3_url}/encode/dense",
            json={"texts": ["preflight warmup"], "max_length": 64, "batch_size": 1},
            timeout=120.0,
        )
        if warmup_resp.status_code == 200:
            data = warmup_resp.json()
            logger.info("Preflight BGE-M3 warmup OK (%.3fs)", data.get("processing_time", 0))
        else:
            logger.warning("Preflight BGE-M3 warmup failed: %s", warmup_resp.status_code)
        return True

    if name == "postgres":
        try:
            conn = await asyncpg.connect(config.realestate_database_url, timeout=5)
            try:
                await conn.fetchval("SELECT 1")
                logger.info("Preflight Postgres: database reachable")
                return True
            finally:
                await conn.close()
        except asyncpg.InvalidCatalogNameError:
            logger.warning(
                "Preflight WARN: Postgres database does not exist (user features will use defaults)"
            )
            return False
        except Exception as exc:
            logger.warning("Preflight WARN: Postgres unreachable — %s", exc)
            return False

    if name == "litellm":
        # Health endpoint is at proxy root, not under /v1
        base = config.llm_base_url.rstrip("/").removesuffix("/v1")
        resp = await client.get(f"{base}/health/liveliness")
        if resp.status_code != 200:
            logger.error("Preflight FAIL: LiteLLM — %s", resp.status_code)
            return False
        return True

    if name == "langfuse":
        from .observability import get_langfuse_client

        lf = get_langfuse_client()
        return lf is not None

    logger.warning("Preflight: unknown dependency %r", name)
    return False


async def _check_critical_with_retry(
    dep_name: str, config: BotConfig, client: httpx.AsyncClient
) -> bool:
    """Check a critical dependency with tenacity retry."""

    @retry(
        stop=stop_after_attempt(CRITICAL_RETRIES),
        wait=wait_fixed(CRITICAL_RETRY_DELAY),
        reraise=True,
    )
    async def _attempt() -> bool:
        result = await _check_single_dep(dep_name, config, client)
        if not result:
            msg = f"{dep_name} check returned False"
            raise RuntimeError(msg)
        return result

    try:
        return await _attempt()
    except Exception as e:
        logger.error(
            "Preflight FAIL: %s [CRITICAL] after %d attempts — %s",
            dep_name,
            CRITICAL_RETRIES,
            e,
        )
        return False


async def check_dependencies(config: BotConfig) -> dict[str, bool]:
    """Check all bot dependencies with retry logic for CRITICAL ones.

    CRITICAL deps (redis, qdrant, bge_m3) are retried up to CRITICAL_RETRIES
    times with CRITICAL_RETRY_DELAY between attempts.

    OPTIONAL deps (litellm, langfuse) are checked once — failures are logged
    as warnings but do not block startup.

    Returns:
        Status dict mapping dep name to pass/fail.

    Raises:
        PreflightError: If any CRITICAL dep fails after all retries.
    """
    results: dict[str, bool] = {}
    timeout = httpx.Timeout(10.0)

    # Order matters: redis_cache depends on redis
    dep_order = ["redis", "redis_cache", "qdrant", "bge_m3", "postgres", "litellm", "langfuse"]

    async with httpx.AsyncClient(timeout=timeout) as client:
        for dep_name in dep_order:
            level = DEP_CLASSIFICATION.get(dep_name, DepLevel.OPTIONAL)

            # redis_cache depends on redis — skip if redis failed
            if dep_name == "redis_cache" and not results.get("redis"):
                results["redis_cache"] = False
                logger.warning("Preflight SKIP: Redis cache verify (Redis unreachable)")
                continue

            if level == DepLevel.CRITICAL:
                results[dep_name] = await _check_critical_with_retry(dep_name, config, client)
            else:
                # Single attempt for optional deps
                try:
                    results[dep_name] = await _check_single_dep(dep_name, config, client)
                except Exception as e:
                    logger.warning("Preflight WARN: %s [OPTIONAL] — %s", dep_name, e)
                    results[dep_name] = False

    # Log summary
    for dep_name, passed in results.items():
        level = DEP_CLASSIFICATION.get(dep_name, DepLevel.OPTIONAL)
        status = "OK" if passed else "FAIL"
        logger.info("Preflight %s: %s [%s]", status, dep_name, level.value)

    # Enforce critical deps
    critical_failures = [
        name
        for name, passed in results.items()
        if not passed and DEP_CLASSIFICATION.get(name) == DepLevel.CRITICAL
    ]
    if critical_failures:
        raise PreflightError(critical_failures)

    # Warn about optional failures
    optional_failures = [
        name
        for name, passed in results.items()
        if not passed and DEP_CLASSIFICATION.get(name) == DepLevel.OPTIONAL
    ]
    if optional_failures:
        logger.warning(
            "Preflight: optional deps unavailable (bot will continue): %s",
            optional_failures,
        )
    else:
        logger.info("Preflight: all dependencies OK")

    return results
