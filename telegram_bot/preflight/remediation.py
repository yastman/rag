"""Preflight remediation helpers: deep checks, validation, and credential redaction."""

import contextlib
import inspect
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient, models


logger = logging.getLogger(__name__)

_REDIS_URL_CREDENTIALS_RE = re.compile(r"(rediss?://)([^@\s]+)@")
_REDIS_AUTH_TOKENS = (
    "invalid username-password pair",
    "wrongpass",
    "authentication required",
    "noauth",
)
_EMPTY_EXCEPTION_MESSAGE = "<empty exception message>"

# Cache key prefixes used by CacheService (see telegram_bot/services/cache.py)
# Used for synthetic write/read/ttl/delete verification at startup.
CACHE_KEY_PREFIXES = [
    "sparse:",
    "search:",
    "rerank:",
    "conversation:",
]

_DEFAULT_COLBERT_COVERAGE_WARN_THRESHOLD = 0.995

# Apartments collection role marker for the two-collection readiness gate.
_APARTMENTS_ROLE = "apartments"


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


def _exception_message_with_type(exc: BaseException) -> str:
    """Render exception type and message with a non-empty fallback."""
    exc_type = type(exc).__name__
    message = str(exc).strip()
    if message:
        return f"{exc_type}: {message}"
    repr_message = repr(exc)
    if repr_message and repr_message != f"{exc_type}()":
        return f"{exc_type}: {repr_message}"
    return f"{exc_type}: {_EMPTY_EXCEPTION_MESSAGE}"


def _redact_redis_credentials(text: str) -> str:
    return _REDIS_URL_CREDENTIALS_RE.sub(r"\1***@", text)


def _is_redis_auth_failure(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in _REDIS_AUTH_TOKENS)


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
        details["error"] = _redact_redis_credentials(str(exc))
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
                errors.append(f"{prefix} error: {_redact_redis_credentials(str(exc))}")
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


async def _qdrant_check_colbert_coverage(
    qdrant_client: AsyncQdrantClient, info: Any, collection: str
) -> None:
    """Log ColBERT coverage — advisory only, never raises."""
    dense_vectors = info.config.params.vectors
    if "colbert" not in (dense_vectors.keys() if isinstance(dense_vectors, dict) else set()):
        logger.warning(
            "Preflight WARN: Qdrant collection %s missing 'colbert' vector "
            "(server-side ColBERT reranking unavailable, RRF fallback active)",
            collection,
        )
        return
    if not info.points_count:
        return
    try:
        with_colbert = await qdrant_client.count(
            collection_name=collection,
            count_filter=models.Filter(must=[models.HasVectorCondition(has_vector="colbert")]),
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
            _exception_message_with_type(exc),
        )


async def _qdrant_validate_collection(
    qdrant_client: AsyncQdrantClient, collection: str, role: str = "knowledge"
) -> tuple[bool, str | None]:
    """Validate one collection against its explicit readiness contract (#3202).

    Checks collection existence, required vector names and dimensions, payload
    indexes, and a non-empty point count. Read-only: a missing collection is an
    actionable failure, never silently auto-created (empty data would only
    defer the failure to the first query).

    Returns (ok, reason) where reason aggregates every contract violation.
    """
    # Lazy import keeps this module's import graph qdrant_client-only.
    from src.runtime.qdrant.readiness import (
        apartments_contract,
        knowledge_contract,
        validate_collection,
    )

    contract = (
        apartments_contract().with_collection_name(collection)
        if role == _APARTMENTS_ROLE
        else knowledge_contract(collection)
    )
    readiness = await validate_collection(qdrant_client, contract)

    if readiness.points_count is not None:
        logger.info(
            "Preflight Qdrant: role=%s, collection=%s, points=%s",
            role,
            collection,
            readiness.points_count,
        )
        # Advisory only — ColBERT absence degrades to the RRF fallback path.
        info = await qdrant_client.get_collection(collection)
        await _qdrant_check_colbert_coverage(qdrant_client, info, collection)

    if readiness.ok:
        return True, None

    reason = "; ".join(f.render() for f in readiness.failures)
    logger.error(
        "Preflight FAIL: Qdrant %s collection '%s' is not ready — %s",
        role,
        collection,
        reason,
    )
    return False, reason


async def _qdrant_validate_product_collections(
    qdrant_client: AsyncQdrantClient,
    knowledge_collection: str,
) -> tuple[bool, str | None]:
    """Prove BOTH product collections are ready before polling (#3202).

    The configured knowledge collection and the hard-coded ``apartments``
    collection are validated against their explicit contracts. Failures from
    both are aggregated so one startup report lists every actionable problem.
    """
    # Lazy import keeps this module's import graph qdrant_client-only.
    from src.runtime.qdrant.readiness import APARTMENTS_COLLECTION

    knowledge_ok, knowledge_reason = await _qdrant_validate_collection(
        qdrant_client, knowledge_collection, role="knowledge"
    )
    apartments_ok, apartments_reason = await _qdrant_validate_collection(
        qdrant_client, APARTMENTS_COLLECTION, role=_APARTMENTS_ROLE
    )

    if knowledge_ok and apartments_ok:
        logger.info(
            "Preflight Qdrant: both product collections ready (knowledge=%s, apartments=%s)",
            knowledge_collection,
            APARTMENTS_COLLECTION,
        )
        return True, None

    details = [detail for detail in (knowledge_reason, apartments_reason) if detail]
    reason = " | ".join(details)
    return False, reason
