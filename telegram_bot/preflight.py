"""Bot dependency preflight checks with CRITICAL/OPTIONAL classification."""

import contextlib
import inspect
import logging
import os
from enum import StrEnum
from urllib.parse import urlparse

import asyncpg
import httpx
import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient, models
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import BotConfig
from .startup_status import DependencyCheckResult, StartupReport, StartupSeverity, StartupSignal


logger = logging.getLogger(__name__)

# Retry settings for critical deps
CRITICAL_RETRIES = 3
CRITICAL_RETRY_DELAY = 5.0  # seconds
_DEFAULT_COLBERT_COVERAGE_WARN_THRESHOLD = 0.995

# BGE-M3 dense vector dimensionality (used when auto-creating missing collections)
_BGEM3_DENSE_DIM = 1024


def _read_colbert_coverage_warn_threshold() -> float:
    """Read configurable ColBERT coverage warning threshold safely."""
    raw = os.getenv(
        "COLBERT_COVERAGE_WARN_THRESHOLD",
        str(_DEFAULT_COLBERT_COVERAGE_WARN_THRESHOLD),
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid COLBERT_COVERAGE_WARN_THRESHOLD=%r, fallback to %.3f",
            raw,
            _DEFAULT_COLBERT_COVERAGE_WARN_THRESHOLD,
        )
        return _DEFAULT_COLBERT_COVERAGE_WARN_THRESHOLD


COLBERT_COVERAGE_WARN_THRESHOLD = _read_colbert_coverage_warn_threshold()

# Cache key prefixes used by CacheService (see telegram_bot/services/cache.py)
# Used for synthetic write/read/ttl/delete verification at startup.
CACHE_KEY_PREFIXES = [
    "sparse:",
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

_DEP_REMEDIATION: dict[str, str] = {
    "redis": "start Redis and verify REDIS_PASSWORD / redis_url",
    "redis_cache": "restore Redis cache write/read path",
    "qdrant": "start Qdrant and verify collection configuration",
    "bge_m3": "start the repo-local BGE-M3 service and verify /health and /encode/dense",
    "postgres": "start PostgreSQL or accept degraded user-feature mode",
    "litellm": "restore LiteLLM proxy readiness or accept degraded generation path",
    "langfuse": "restore Langfuse credentials/connectivity or accept disabled tracing",
}


def _postgres_local_remediation(database_url: str) -> str | None:
    """Return a clearer hint when native local Postgres is the optional target."""
    parsed = urlparse(database_url)
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        return None
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    return (
        f"Postgres unreachable at {host}:{port}; this is optional for native bot runs. "
        "If you need user features locally, start a compose stack that publishes Postgres "
        "via compose.yml:compose.dev.yml."
    )


class PreflightError(SystemExit):
    """Raised when a CRITICAL dependency is unreachable after retries."""

    def __init__(self, failed_deps: list[str], report: StartupReport | None = None):
        self.failed_deps = failed_deps
        self.report = report or StartupReport()
        msg = (
            f"CRITICAL preflight failure — cannot start bot. "
            f"Unreachable after {CRITICAL_RETRIES} attempts: {', '.join(failed_deps)}"
        )
        super().__init__(msg)


def _build_dependency_report(results: dict[str, bool]) -> StartupReport:
    report = StartupReport()
    for dep_name, passed in results.items():
        if passed:
            continue
        level = DEP_CLASSIFICATION.get(dep_name, DepLevel.OPTIONAL)
        severity = (
            StartupSeverity.FAILED if level == DepLevel.CRITICAL else StartupSeverity.DEGRADED
        )
        report.add(
            StartupSignal(
                source=dep_name,
                severity=severity,
                summary=f"{level.value} dependency unavailable",
                remediation=_DEP_REMEDIATION.get(dep_name),
            )
        )
    return report


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
        ping_result = r.ping()
        if inspect.isawaitable(ping_result):
            await ping_result
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


async def _ensure_qdrant_collection(qdrant: AsyncQdrantClient, collection_name: str) -> None:
    """Create Qdrant collection with the standard BGE-M3 vector schema.

    Schema mirrors gdrive_documents_bge: dense (1024-dim COSINE), colbert
    (multi-vector MAX_SIM), and bm42 (sparse IDF).  The collection will be
    empty — ingestion should populate it afterwards.
    """
    await qdrant.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": models.VectorParams(
                size=_BGEM3_DENSE_DIM,
                distance=models.Distance.COSINE,
            ),
            "colbert": models.VectorParams(
                size=_BGEM3_DENSE_DIM,
                distance=models.Distance.COSINE,
                multivector_config=models.MultiVectorConfig(
                    comparator=models.MultiVectorComparator.MAX_SIM
                ),
                hnsw_config=models.HnswConfigDiff(m=0),
            ),
        },
        sparse_vectors_config={
            "bm42": models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            ),
        },
    )


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
        getter = getattr(config, "get_collection_name", None)
        collection = getter() if callable(getter) else config.qdrant_collection
        scheme = urlparse(config.qdrant_url).scheme.lower()
        effective_key = config.qdrant_api_key if scheme == "https" else None
        qdrant = AsyncQdrantClient(
            url=config.qdrant_url,
            api_key=effective_key,
            timeout=config.qdrant_timeout,
            prefer_grpc=True,
        )
        try:
            exists = await qdrant.collection_exists(collection)
            if not exists:
                logger.warning(
                    "Preflight WARN: Qdrant collection %s not found via SDK existence check; "
                    "creating default schema",
                    collection,
                )
                try:
                    await _ensure_qdrant_collection(qdrant, collection)
                    logger.info(
                        "Preflight Qdrant: collection %s created (empty, ready for ingestion)",
                        collection,
                    )
                    return True
                except Exception as create_exc:
                    logger.error(
                        "Preflight FAIL: Qdrant — could not create collection %s: %s",
                        collection,
                        create_exc,
                    )
                    return False

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
            logger.error("Preflight FAIL: BGE-M3 repo-local health contract — %s", resp.status_code)
            return False
        # Warm encode to verify the repo-local model service is actually ready to serve embeddings.
        warmup_resp = await client.post(
            f"{config.bge_m3_url}/encode/dense",
            json={"texts": ["preflight warmup"], "max_length": 64, "batch_size": 1},
            timeout=120.0,
        )
        if warmup_resp.status_code == 200:
            data = warmup_resp.json()
            logger.info(
                "Preflight BGE-M3 repo-local warmup OK (%.3fs)",
                data.get("processing_time", 0),
            )
        else:
            logger.warning(
                "Preflight BGE-M3 repo-local warmup failed: %s",
                warmup_resp.status_code,
            )
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
                "Preflight WARN: Postgres database does not exist yet; startup may auto-create "
                "it before enabling user features"
            )
            return True
        except Exception as exc:
            remediation = _postgres_local_remediation(config.realestate_database_url)
            if remediation:
                logger.warning("Preflight WARN: %s — %s", remediation, exc)
            else:
                logger.warning("Preflight WARN: Postgres unreachable — %s", exc)
            return False

    if name == "litellm":
        # Health endpoint is at proxy root, not under /v1
        base = config.llm_base_url.rstrip("/").removesuffix("/v1")
        resp = await client.get(f"{base}/health/readiness")
        if resp.status_code != 200:
            logger.error("Preflight FAIL: LiteLLM proxy readiness — %s", resp.status_code)
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


async def check_dependencies(
    config: BotConfig,
    *,
    log_summary: bool = True,
) -> DependencyCheckResult:
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

    # Log per-dependency status
    for dep_name, passed in results.items():
        level = DEP_CLASSIFICATION.get(dep_name, DepLevel.OPTIONAL)
        status = "OK" if passed else "FAIL"
        logger.info("Preflight %s: %s [%s]", status, dep_name, level.value)

    report = _build_dependency_report(results)
    if log_summary:
        if report.final_severity is StartupSeverity.FAILED:
            logger.error(report.render())
        elif report.final_severity is StartupSeverity.DEGRADED:
            logger.warning(report.render())
        else:
            logger.info(report.render())

    # Enforce critical deps
    critical_failures = [
        name
        for name, passed in results.items()
        if not passed and DEP_CLASSIFICATION.get(name) == DepLevel.CRITICAL
    ]
    if critical_failures:
        raise PreflightError(critical_failures, report=report)

    return DependencyCheckResult(results, report=report)
