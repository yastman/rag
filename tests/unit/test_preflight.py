"""Unit tests for telegram_bot/preflight.py — dependency preflight checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.preflight import (
    CACHE_KEY_PREFIXES,
    CRITICAL_RETRIES,
    PreflightError,
    _check_redis_deep,
    _check_single_dep,
    _verify_cache_synthetic,
    check_dependencies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> MagicMock:
    """Create a minimal mock BotConfig with sensible defaults."""
    cfg = MagicMock()
    cfg.redis_url = overrides.get("redis_url", "redis://localhost:6379")
    cfg.qdrant_url = overrides.get("qdrant_url", "http://localhost:6333")
    cfg.qdrant_api_key = overrides.get("qdrant_api_key")
    cfg.qdrant_collection = overrides.get("qdrant_collection", "test_col")
    cfg.qdrant_timeout = overrides.get("qdrant_timeout", 30)
    cfg.bge_m3_url = overrides.get("bge_m3_url", "http://localhost:8000")
    cfg.llm_base_url = overrides.get("llm_base_url", "http://localhost:4000")
    cfg.realestate_database_url = overrides.get(
        "realestate_database_url", "postgresql://postgres:postgres@localhost:5432/realestate"
    )
    return cfg


# ===========================================================================
# PreflightError
# ===========================================================================


class TestPreflightError:
    """PreflightError is a SystemExit subclass with dep list."""

    def test_is_system_exit(self):
        err = PreflightError(["redis"])
        assert isinstance(err, SystemExit)

    def test_message_contains_failed_dep(self):
        err = PreflightError(["qdrant", "bge_m3"])
        msg = str(err)
        assert "qdrant" in msg
        assert "bge_m3" in msg

    def test_failed_deps_attribute(self):
        err = PreflightError(["redis", "redis_cache"])
        assert err.failed_deps == ["redis", "redis_cache"]

    def test_message_mentions_retry_count(self):
        err = PreflightError(["redis"])
        assert str(CRITICAL_RETRIES) in str(err)


# ===========================================================================
# _check_redis_deep
# ===========================================================================


class TestCheckRedisDeep:
    """Tests for _check_redis_deep(redis_url)."""

    async def test_success_returns_details(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.info = AsyncMock(
            side_effect=lambda section: {
                "memory": {
                    "used_memory_human": "1.5M",
                    "maxmemory_policy": "volatile-lfu",
                },
                "clients": {"connected_clients": 3},
                "server": {"redis_version": "7.2.4"},
                "keyspace": {"db0": {"keys": 100, "expires": 50}},
            }[section]
        )
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is True
        assert details["ping"] == "ok"
        assert details["used_memory_human"] == "1.5M"
        assert details["maxmemory_policy"] == "volatile-lfu"
        assert details["connected_clients"] == "3"
        assert details["redis_version"] == "7.2.4"

    async def test_ping_failure_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is False
        assert "error" in details

    async def test_noeviction_policy_warning(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.info = AsyncMock(
            side_effect=lambda section: {
                "memory": {
                    "used_memory_human": "1M",
                    "maxmemory_policy": "noeviction",
                },
                "clients": {"connected_clients": 1},
                "server": {"redis_version": "7.0.0"},
                "keyspace": {},
            }[section]
        )
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is True
        assert "policy_warning" in details
        assert "noeviction" in details["policy_warning"]

    async def test_empty_keyspace_recorded(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.info = AsyncMock(
            side_effect=lambda section: {
                "memory": {
                    "used_memory_human": "512K",
                    "maxmemory_policy": "volatile-lfu",
                },
                "clients": {"connected_clients": 1},
                "server": {"redis_version": "7.0.0"},
                "keyspace": {},
            }[section]
        )
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is True
        assert details["keyspace_db0"] == "empty"


# ===========================================================================
# _verify_cache_synthetic
# ===========================================================================


class TestVerifyCacheSynthetic:
    """Tests for _verify_cache_synthetic(redis_url)."""

    async def test_success_all_prefixes(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=["preflight_ok", None] * len(CACHE_KEY_PREFIXES))
        mock_redis.ttl = AsyncMock(return_value=28)
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, errors = await _verify_cache_synthetic("redis://localhost")

        assert passed is True
        assert errors == []

    async def test_set_raises_reports_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("write failed"))
        mock_redis.delete = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, errors = await _verify_cache_synthetic("redis://localhost")

        assert passed is False
        assert len(errors) == len(CACHE_KEY_PREFIXES)
        assert any("write failed" in e for e in errors)

    async def test_read_mismatch_reports_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(return_value="wrong_value")
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, errors = await _verify_cache_synthetic("redis://localhost")

        assert passed is False
        assert any("mismatch" in e for e in errors)

    async def test_ttl_not_set_reports_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(return_value="preflight_ok")
        mock_redis.ttl = AsyncMock(return_value=-1)
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, errors = await _verify_cache_synthetic("redis://localhost")

        assert passed is False
        assert any("TTL" in e for e in errors)

    async def test_delete_failure_reports_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(return_value="preflight_ok")
        mock_redis.ttl = AsyncMock(return_value=25)
        mock_redis.delete = AsyncMock(return_value=0)
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, errors = await _verify_cache_synthetic("redis://localhost")

        assert passed is False
        assert any("delete returned 0" in e for e in errors)


# ===========================================================================
# _check_single_dep
# ===========================================================================


class TestCheckSingleDep:
    """Tests for _check_single_dep(name, config, client)."""

    async def test_redis_delegates_to_check_redis_deep(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "telegram_bot.preflight._check_redis_deep",
            new_callable=AsyncMock,
            return_value=(True, {"ping": "ok"}),
        ) as mock_deep:
            result = await _check_single_dep("redis", config, client)

        assert result is True
        mock_deep.assert_awaited_once_with(config.redis_url)

    async def test_redis_cache_delegates_to_verify_cache(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "telegram_bot.preflight._verify_cache_synthetic",
            new_callable=AsyncMock,
            return_value=(True, []),
        ) as mock_verify:
            result = await _check_single_dep("redis_cache", config, client)

        assert result is True
        mock_verify.assert_awaited_once_with(config.redis_url)

    async def test_qdrant_collection_ok(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        mock_info = MagicMock()
        mock_info.points_count = 100
        mock_info.config.params.vectors = {"dense": MagicMock(), "colbert": MagicMock()}
        mock_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        mock_qdrant_client = AsyncMock()
        mock_qdrant_client.get_collection = AsyncMock(return_value=mock_info)
        mock_qdrant_client.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            result = await _check_single_dep("qdrant", config, client)

        assert result is True
        mock_qdrant_client.get_collection.assert_awaited_once_with(config.qdrant_collection)
        mock_qdrant_client.close.assert_awaited_once()

    async def test_qdrant_exception_fails(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        mock_qdrant_client = AsyncMock()
        mock_qdrant_client.get_collection = AsyncMock(side_effect=Exception("not found"))
        mock_qdrant_client.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            result = await _check_single_dep("qdrant", config, client)

        assert result is False

    async def test_bge_m3_health_ok(self):
        config = _make_config()
        health_resp = MagicMock()
        health_resp.status_code = 200
        warmup_resp = MagicMock()
        warmup_resp.status_code = 200
        warmup_resp.json = MagicMock(return_value={"processing_time": 0.5})

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=health_resp)
        client.post = AsyncMock(return_value=warmup_resp)

        result = await _check_single_dep("bge_m3", config, client)

        assert result is True
        client.get.assert_awaited_once_with(f"{config.bge_m3_url}/health")
        client.post.assert_awaited_once()

    async def test_bge_m3_non_200_fails(self):
        config = _make_config()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _check_single_dep("bge_m3", config, client)
        assert result is False

    async def test_bge_m3_warmup_failure_still_passes(self):
        """Warmup encode failure is non-fatal — health check already passed."""
        config = _make_config()
        health_resp = MagicMock()
        health_resp.status_code = 200
        warmup_resp = MagicMock()
        warmup_resp.status_code = 500

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=health_resp)
        client.post = AsyncMock(return_value=warmup_resp)

        result = await _check_single_dep("bge_m3", config, client)
        assert result is True

    async def test_litellm_health_ok(self):
        config = _make_config()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _check_single_dep("litellm", config, client)

        assert result is True
        client.get.assert_awaited_once_with(f"{config.llm_base_url}/health/liveliness")

    async def test_litellm_non_200_fails(self):
        config = _make_config()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_resp)

        result = await _check_single_dep("litellm", config, client)
        assert result is False

    async def test_langfuse_uses_get_langfuse_client(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "telegram_bot.observability.get_langfuse_client",
            return_value=MagicMock(),
        ):
            result = await _check_single_dep("langfuse", config, client)

        assert result is True

    async def test_langfuse_none_means_fail(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch(
            "telegram_bot.observability.get_langfuse_client",
            return_value=None,
        ):
            result = await _check_single_dep("langfuse", config, client)

        assert result is False

    async def test_unknown_dep_returns_false(self):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        result = await _check_single_dep("nonexistent_service", config, client)
        assert result is False


# ===========================================================================
# check_dependencies (orchestrator)
# ===========================================================================


class TestCheckDependencies:
    """Tests for check_dependencies(config) — main orchestrator."""

    async def test_all_pass(self):
        config = _make_config()

        with (
            patch(
                "telegram_bot.preflight._check_critical_with_retry",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "telegram_bot.preflight._check_single_dep",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            results = await check_dependencies(config)

        assert all(results.values())
        assert "redis" in results
        assert "langfuse" in results

    async def test_critical_failure_raises_preflight_error(self):
        config = _make_config()

        async def fake_critical(name, cfg, client):
            return name != "redis"

        async def fake_optional(name, cfg, client):
            return True

        with (
            patch("telegram_bot.preflight._check_critical_with_retry", side_effect=fake_critical),
            patch("telegram_bot.preflight._check_single_dep", side_effect=fake_optional),
            pytest.raises(PreflightError) as exc_info,
        ):
            await check_dependencies(config)

        assert "redis" in exc_info.value.failed_deps

    async def test_optional_failure_does_not_raise(self):
        config = _make_config()

        async def fake_optional(name, cfg, client):
            return name != "langfuse"

        with (
            patch(
                "telegram_bot.preflight._check_critical_with_retry",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("telegram_bot.preflight._check_single_dep", side_effect=fake_optional),
        ):
            results = await check_dependencies(config)

        assert results["langfuse"] is False
        # No PreflightError raised — optional deps don't block

    async def test_retry_logic_first_fail_second_pass(self):
        """Test that tenacity retry in _check_critical_with_retry eventually passes."""
        config = _make_config()
        call_counts: dict[str, int] = {}

        async def fake_check(name, cfg, client):
            call_counts[name] = call_counts.get(name, 0) + 1
            # qdrant fails first attempt, passes second
            return not (name == "qdrant" and call_counts[name] < 2)

        with (
            patch("telegram_bot.preflight._check_single_dep", side_effect=fake_check),
            patch("telegram_bot.preflight.CRITICAL_RETRY_DELAY", 0),
        ):
            results = await check_dependencies(config)

        assert results["qdrant"] is True
        assert call_counts["qdrant"] == 2  # retried once

    async def test_redis_cache_skipped_when_redis_fails(self):
        config = _make_config()

        async def fake_critical(name, cfg, client):
            return name != "redis"

        with (
            patch("telegram_bot.preflight._check_critical_with_retry", side_effect=fake_critical),
            patch("telegram_bot.preflight._check_single_dep", new_callable=AsyncMock),
            pytest.raises(PreflightError),
        ):
            await check_dependencies(config)

    async def test_critical_dep_exception_treated_as_failure(self):
        config = _make_config()

        async def fake_critical(name, cfg, client):
            return name != "bge_m3"

        with (
            patch("telegram_bot.preflight._check_critical_with_retry", side_effect=fake_critical),
            patch(
                "telegram_bot.preflight._check_single_dep",
                new_callable=AsyncMock,
                return_value=True,
            ),
            pytest.raises(PreflightError) as exc_info,
        ):
            await check_dependencies(config)

        assert "bge_m3" in exc_info.value.failed_deps


# ===========================================================================
# PostgreSQL preflight check
# ===========================================================================


# ===========================================================================
# Qdrant vector name validation
# ===========================================================================


class TestQdrantVectorValidation:
    """Preflight validates required named vectors in collection."""

    async def test_qdrant_warns_when_colbert_vector_missing(self, caplog):
        """Missing colbert vector logged as warning, but check still passes."""
        import logging

        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 278
        mock_collection_info.config.params.vectors = {"dense": MagicMock()}
        mock_collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant),
            caplog.at_level(logging.WARNING),
        ):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is True
            assert "colbert" in caplog.text.lower()

    async def test_qdrant_no_warning_when_all_vectors_present(self, caplog):
        """No warning when dense + bm42 + colbert all present."""
        import logging

        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 278
        mock_collection_info.config.params.vectors = {
            "dense": MagicMock(),
            "colbert": MagicMock(),
        }
        mock_collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant),
            caplog.at_level(logging.WARNING),
        ):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is True
            assert "missing" not in caplog.text.lower()

    async def test_qdrant_fails_when_dense_missing(self):
        """Missing dense vector causes check to fail."""
        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 278
        mock_collection_info.config.params.vectors = {}
        mock_collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is False

    async def test_qdrant_fails_when_bm42_missing(self):
        """Missing bm42 sparse vector causes check to fail."""
        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 278
        mock_collection_info.config.params.vectors = {"dense": MagicMock()}
        mock_collection_info.config.params.sparse_vectors = {}
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is False


# ===========================================================================
# Qdrant preflight client config
# ===========================================================================


class TestQdrantPreflightClient:
    """Preflight Qdrant client uses timeout and gRPC."""

    async def test_qdrant_preflight_uses_timeout_and_grpc(self):
        """Preflight uses BotConfig timeout and prefer_grpc=True."""
        config = _make_config(qdrant_timeout=42)
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 100
        mock_collection_info.config.params.vectors = {"dense": MagicMock()}
        mock_collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with patch(
            "telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant
        ) as MockClient:
            client = AsyncMock()
            await _check_single_dep("qdrant", config, client)

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("timeout") == config.qdrant_timeout
            assert call_kwargs.get("prefer_grpc") is True


class TestPostgresPreflight:
    """Postgres preflight check validates database existence."""

    async def test_postgres_check_passes_when_db_exists(self):
        """Preflight passes when Postgres connection succeeds."""
        config = _make_config(realestate_database_url="postgresql://u:p@localhost/realestate")
        with patch("telegram_bot.preflight.asyncpg") as mock_asyncpg:
            mock_conn = AsyncMock()
            mock_conn.fetchval = AsyncMock(return_value=1)
            mock_conn.close = AsyncMock()
            mock_asyncpg.connect = AsyncMock(return_value=mock_conn)

            client = AsyncMock()
            result = await _check_single_dep("postgres", config, client)
            assert result is True

    async def test_postgres_check_fails_when_db_missing(self):
        """Preflight fails when database does not exist."""
        import asyncpg as real_asyncpg

        config = _make_config(realestate_database_url="postgresql://u:p@localhost/realestate")
        with patch("telegram_bot.preflight.asyncpg") as mock_asyncpg:
            mock_asyncpg.connect = AsyncMock(
                side_effect=real_asyncpg.InvalidCatalogNameError(
                    'database "realestate" does not exist'
                )
            )
            mock_asyncpg.InvalidCatalogNameError = real_asyncpg.InvalidCatalogNameError

            client = AsyncMock()
            result = await _check_single_dep("postgres", config, client)
            assert result is False

    async def test_postgres_in_dep_classification_as_optional(self):
        """Postgres is OPTIONAL — bot degrades without it."""
        from telegram_bot.preflight import DEP_CLASSIFICATION, DepLevel

        assert DEP_CLASSIFICATION.get("postgres") == DepLevel.OPTIONAL


class TestPostgresOptionalBehavior:
    """Postgres failure does not block startup."""

    async def test_postgres_optional_does_not_block_startup(self):
        """Postgres failure does not raise PreflightError."""
        config = _make_config(realestate_database_url="postgresql://u:p@localhost/missing")

        async def fake_optional(name, cfg, client):
            return False

        with (
            patch(
                "telegram_bot.preflight._check_critical_with_retry",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("telegram_bot.preflight._check_single_dep", side_effect=fake_optional),
        ):
            results = await check_dependencies(config)

        assert results["postgres"] is False
