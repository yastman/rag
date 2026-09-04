"""Unit tests for telegram_bot/preflight.py — dependency preflight checks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from telegram_bot.preflight import (
    CACHE_KEY_PREFIXES,
    CRITICAL_RETRIES,
    DEP_CLASSIFICATION,
    PreflightError,
    _build_dependency_report,
    _check_redis_deep,
    _check_single_dep,
    _read_colbert_coverage_warn_threshold,
    _verify_cache_synthetic,
    check_dependencies,
)
from telegram_bot.startup_status import StartupReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schema_obj(type_name: str) -> SimpleNamespace:
    """Minimal Qdrant payload-schema entry with a typed data_type."""
    return SimpleNamespace(data_type=SimpleNamespace(value=type_name))


def _contract_payload_schema(role: str) -> dict:
    """Payload-schema dict satisfying the role's readiness contract (#3202)."""
    from src.runtime.qdrant.readiness import apartments_contract, knowledge_contract

    contract = apartments_contract() if role == "apartments" else knowledge_contract("k")
    return {index.field_name: _schema_obj(index.schema_type) for index in contract.payload_indexes}


def _collection_info(
    points: int = 100,
    dense: tuple[str, ...] = ("dense", "colbert"),
    sparse: tuple[str, ...] = ("bm42",),
    payload_schema: dict | None = None,
    dense_size: int = 1024,
) -> MagicMock:
    """Collection info matching the knowledge readiness contract by default."""
    info = MagicMock()
    info.points_count = points
    info.config.params.vectors = {
        name: SimpleNamespace(size=dense_size, multivector_config=None) for name in dense
    }
    info.config.params.sparse_vectors = {name: MagicMock() for name in sparse}
    info.payload_schema = (
        payload_schema if payload_schema is not None else _contract_payload_schema("knowledge")
    )
    return info


def _ready_qdrant_client(
    knowledge_info: MagicMock | None = None,
    apartments_info: MagicMock | None = None,
    knowledge_name: str = "test_col",
    exists: bool = True,
) -> AsyncMock:
    """Async Qdrant client mock serving per-collection info for both roles.

    Routes ``get_collection`` by collection name so the two-collection readiness
    gate (#3202) sees a contract-valid knowledge collection and a contract-valid
    apartments collection.
    """
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=exists)
    infos = {
        knowledge_name: knowledge_info or _collection_info(),
        "apartments": apartments_info
        or _collection_info(payload_schema=_contract_payload_schema("apartments")),
    }

    async def _get_collection(collection: str) -> MagicMock:
        return infos[collection]

    client.get_collection = AsyncMock(side_effect=_get_collection)
    client.count = AsyncMock(return_value=MagicMock(count=100))
    client.close = AsyncMock()
    return client


def _make_config(**overrides) -> MagicMock:
    """Create a minimal mock BotConfig with sensible defaults."""
    cfg = MagicMock()
    cfg.redis_url = overrides.get("redis_url", "redis://localhost:6379")
    cfg.qdrant_url = overrides.get("qdrant_url", "http://localhost:6333")
    cfg.qdrant_api_key = overrides.get("qdrant_api_key")
    cfg.qdrant_collection = overrides.get("qdrant_collection", "test_col")
    effective_collection = overrides.get("effective_collection", cfg.qdrant_collection)
    cfg.get_collection_name = MagicMock(return_value=effective_collection)
    cfg.qdrant_timeout = overrides.get("qdrant_timeout", 30)
    cfg.bge_m3_url = overrides.get("bge_m3_url", "http://localhost:8000")
    cfg.llm_base_url = overrides.get("llm_base_url", "")
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

    def test_report_attribute_defaults_to_startup_report(self):
        err = PreflightError(["redis"])
        assert isinstance(err.report, StartupReport)


class TestColbertCoverageWarnThreshold:
    """Threshold parser tolerates invalid env values with fallback."""

    def test_invalid_env_uses_default(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("COLBERT_COVERAGE_WARN_THRESHOLD", "oops")
        with caplog.at_level(logging.WARNING):
            value = _read_colbert_coverage_warn_threshold()

        assert value == pytest.approx(0.995)
        assert "invalid colbert_coverage_warn_threshold" in caplog.text.lower()

    def test_valid_env_value_is_used(self, monkeypatch):
        monkeypatch.setenv("COLBERT_COVERAGE_WARN_THRESHOLD", "0.87")
        value = _read_colbert_coverage_warn_threshold()
        assert value == pytest.approx(0.87)


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

    async def test_sync_ping_result_is_accepted(self):
        mock_redis = AsyncMock()
        mock_redis.ping = Mock(return_value=True)
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

    async def test_ping_failure_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is False
        assert "error" in details

    async def test_error_text_redacts_redis_password_from_uri(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(
            side_effect=RuntimeError("error for redis://:supersecret@localhost:6379")
        )
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is False
        assert "supersecret" not in details["error"]
        assert "redis://***@localhost:6379" in details["error"]

    async def test_error_text_redacts_redis_password_from_rediss_uri(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(
            side_effect=RuntimeError("error for rediss://:supersecret@localhost:6379")
        )
        mock_redis.aclose = AsyncMock()

        with patch("telegram_bot.preflight.aioredis.from_url", return_value=mock_redis):
            passed, details = await _check_redis_deep("redis://localhost")

        assert passed is False
        assert "supersecret" not in details["error"]
        assert "rediss://***@localhost:6379" in details["error"]

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


class TestPostgresRemediation:
    async def test_local_connection_refused_logs_local_runtime_remediation(self, caplog):
        config = _make_config(realestate_database_url="postgresql://u:p@localhost:5432/realestate")
        client = AsyncMock()

        with (
            patch(
                "telegram_bot.preflight.asyncpg.connect",
                AsyncMock(side_effect=ConnectionRefusedError(111, "Connection refused")),
            ),
            caplog.at_level("WARNING"),
        ):
            result = await _check_single_dep("postgres", config, client)

        assert result is False
        assert "localhost:5432" in caplog.text
        assert "optional for native bot runs" in caplog.text
        assert "--profile postgres" in caplog.text


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

    async def test_redis_auth_error_logs_password_drift_remediation(self, caplog):
        import logging

        config = _make_config(redis_url="redis://:verysecret@localhost:6379/0")
        client = AsyncMock(spec=httpx.AsyncClient)

        with (
            patch(
                "telegram_bot.preflight._check_redis_deep",
                new_callable=AsyncMock,
                return_value=(
                    False,
                    {"error": "invalid username-password pair or user is disabled."},
                ),
            ),
            caplog.at_level(logging.ERROR),
        ):
            result = await _check_single_dep("redis", config, client)

        assert result is False
        assert "make local-redis-recreate" in caplog.text
        assert "REDIS_PASSWORD" in caplog.text
        assert "verysecret" not in caplog.text

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

    async def test_qdrant_uses_collection_exists_before_get_collection(self):
        config = _make_config(qdrant_collection="test_col", effective_collection="test_col_scalar")
        client = AsyncMock(spec=httpx.AsyncClient)

        mock_qdrant_client = _ready_qdrant_client(knowledge_name="test_col_scalar")

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            result = await _check_single_dep("qdrant", config, client)

        assert result is True
        config.get_collection_name.assert_called_once_with()
        checked = [call.args[0] for call in mock_qdrant_client.collection_exists.await_args_list]
        assert checked == ["test_col_scalar", "apartments"]
        checked_collections = [
            call.args[0] for call in mock_qdrant_client.get_collection.await_args_list
        ]
        assert "test_col_scalar" in checked_collections
        assert "apartments" in checked_collections
        mock_qdrant_client.close.assert_awaited_once()

    async def test_qdrant_connection_error_fails(self):
        """Non-404 exceptions (e.g. connection refused) still fail the check."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        mock_qdrant_client = AsyncMock()
        mock_qdrant_client.collection_exists = AsyncMock(return_value=True)
        mock_qdrant_client.get_collection = AsyncMock(side_effect=Exception("Connection refused"))
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

    def test_litellm_proxy_is_not_a_preflight_dependency(self):
        assert "litellm" not in DEP_CLASSIFICATION

    async def test_langfuse_check_removed(self):
        """Langfuse dep check removed in #2969; 'langfuse' is now an unknown dep."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

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
        assert "langfuse" not in results  # removed in #2969

    async def test_critical_failure_raises_preflight_error(self):
        config = _make_config()

        async def fake_critical(name, cfg, client, **_kwargs):
            return name != "redis"

        async def fake_optional(name, cfg, client, **_kwargs):
            return True

        with (
            patch("telegram_bot.preflight._check_critical_with_retry", side_effect=fake_critical),
            patch("telegram_bot.preflight._check_single_dep", side_effect=fake_optional),
            pytest.raises(PreflightError) as exc_info,
        ):
            await check_dependencies(config)

        assert "redis" in exc_info.value.failed_deps
        assert exc_info.value.report.final_severity.name == "FAILED"

    async def test_optional_failure_does_not_raise(self):
        config = _make_config()

        async def fake_optional(name, cfg, client, **_kwargs):
            return name != "postgres"

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
        # No PreflightError raised — optional deps don't block

    async def test_retry_logic_first_fail_second_pass(self):
        """Test that tenacity retry in _check_critical_with_retry eventually passes."""
        config = _make_config()
        call_counts: dict[str, int] = {}

        async def fake_check(name, cfg, client, **_kwargs):
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

        async def fake_critical(name, cfg, client, **_kwargs):
            return name != "redis"

        with (
            patch("telegram_bot.preflight._check_critical_with_retry", side_effect=fake_critical),
            patch("telegram_bot.preflight._check_single_dep", new_callable=AsyncMock),
            pytest.raises(PreflightError),
        ):
            await check_dependencies(config)

    async def test_critical_dep_exception_treated_as_failure(self):
        config = _make_config()

        async def fake_critical(name, cfg, client, **_kwargs):
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
    """Preflight validates required named vectors, dims, and indexes (#3202)."""

    async def test_qdrant_warns_when_colbert_vector_missing(self, caplog):
        """Missing colbert vector logged as warning, but check still passes."""
        import logging

        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=278, dense=("dense",)),
        )

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client),
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
        mock_qdrant_client = _ready_qdrant_client()

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client),
            caplog.at_level(logging.WARNING),
        ):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is True
            assert "missing advisory" not in caplog.text.lower()

    async def test_qdrant_warns_when_colbert_coverage_below_threshold(self, caplog):
        """Low ColBERT point coverage logs warning but does not fail preflight."""
        import logging

        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=200),
        )
        mock_qdrant_client.count = AsyncMock(return_value=MagicMock(count=180))

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client),
            caplog.at_level(logging.WARNING),
        ):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)

        assert result is True
        assert "coverage" in caplog.text.lower()
        assert "90.00%" in caplog.text

    async def test_qdrant_logs_coverage_info_when_threshold_met(self, caplog):
        """Coverage at/above threshold logs informational line."""
        import logging

        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client()
        mock_qdrant_client.count = AsyncMock(return_value=MagicMock(count=100))

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client),
            caplog.at_level(logging.INFO),
        ):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)

        assert result is True
        assert "coverage" in caplog.text.lower()
        assert "100.00%" in caplog.text

    async def test_qdrant_colbert_coverage_failure_warns_without_failing(self, caplog):
        """ColBERT coverage is advisory; count failures should not fail startup."""
        import logging

        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client()
        mock_qdrant_client.count = AsyncMock(side_effect=RuntimeError("count unavailable"))

        with (
            patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client),
            caplog.at_level(logging.WARNING),
        ):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)

        assert result is True
        assert "colbert coverage check failed" in caplog.text.lower()

    async def test_qdrant_fails_when_dense_missing(self):
        """Missing dense vector causes check to fail."""
        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(
                points=278,
                dense=(),
            ),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is False

    async def test_qdrant_fails_when_bm42_missing(self):
        """Missing bm42 sparse vector causes check to fail."""
        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(
                points=278,
                sparse=(),
            ),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is False

    async def test_qdrant_fails_when_dense_dimension_wrong(self):
        """A 768-dim dense vector violates the 1024-dim BGE-M3 contract (#3202)."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=278, dense_size=768),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        assert "dimensional" in failure_reasons["qdrant"]
        assert "1024" in failure_reasons["qdrant"]

    async def test_qdrant_fails_when_payload_index_missing(self):
        """A missing contract payload index is a schema-incompatible failure."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        schema = _contract_payload_schema("knowledge")
        schema.pop("metadata.doc_id")
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=278, payload_schema=schema),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        assert "payload index" in failure_reasons["qdrant"]
        assert "metadata.doc_id" in failure_reasons["qdrant"]

    async def test_qdrant_fails_when_payload_index_type_wrong(self):
        """A payload index with the wrong type is a schema-incompatible failure."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        schema = _contract_payload_schema("knowledge")
        schema["metadata.order"] = _schema_obj("keyword")
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=278, payload_schema=schema),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        assert "metadata.order" in failure_reasons["qdrant"]

    async def test_qdrant_fails_when_knowledge_collection_empty(self):
        """An existing but empty collection stops startup (#3202)."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=0),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        assert "empty" in failure_reasons["qdrant"]

    async def test_qdrant_fails_when_apartments_schema_incompatible(self):
        """Apartments collection with missing payload indexes fails startup."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        schema = _contract_payload_schema("apartments")
        schema.pop("price_eur")
        mock_qdrant_client = _ready_qdrant_client(
            apartments_info=_collection_info(points=5, payload_schema=schema),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        assert "apartments" in failure_reasons["qdrant"]
        assert "price_eur" in failure_reasons["qdrant"]


# ===========================================================================
# Qdrant preflight client config
# ===========================================================================


class TestQdrantPreflightClient:
    """Preflight Qdrant client uses timeout and gRPC."""

    async def test_qdrant_preflight_uses_timeout_and_grpc(self):
        """Preflight uses BotConfig timeout and prefer_grpc=True."""
        config = _make_config(qdrant_timeout=42)
        mock_qdrant_client = _ready_qdrant_client()

        with patch(
            "telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client
        ) as MockClient:
            client = AsyncMock()
            await _check_single_dep("qdrant", config, client)

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("timeout") == config.qdrant_timeout
            assert call_kwargs.get("prefer_grpc") is True

    async def test_qdrant_failure_report_includes_reason(self):
        """Failure detail should propagate into startup summary when qdrant checks fail."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        failure_reasons: dict[str, str] = {}

        with patch(
            "telegram_bot.preflight.AsyncQdrantClient", side_effect=[Exception(), Exception()]
        ):
            result = await _check_single_dep(
                "qdrant",
                config,
                client,
                failure_reasons=failure_reasons,
            )

        assert result is False
        assert "qdrant" in failure_reasons
        assert failure_reasons["qdrant"]
        assert "empty exception message" in failure_reasons["qdrant"].lower()

        report = _build_dependency_report({"qdrant": False}, failures=failure_reasons)
        rendered = report.render()
        assert "qdrant: CRITICAL dependency unavailable" in rendered
        assert "empty exception message" in rendered


class TestPostgresPreflight:
    """Postgres preflight check validates connectivity without blocking recovery paths."""

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

    async def test_postgres_check_allows_missing_db_recovery(self, caplog):
        """Missing DB should stay recoverable so startup can run the auto-create path."""
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
            assert result is True
            assert "auto-create" in caplog.text.lower()

    def test_postgres_in_dep_classification_as_optional(self):
        """Postgres is OPTIONAL — bot degrades without it."""
        from telegram_bot.preflight import DEP_CLASSIFICATION, DepLevel

        assert DEP_CLASSIFICATION.get("postgres") == DepLevel.OPTIONAL


class TestPostgresOptionalBehavior:
    """Postgres failure does not block startup."""

    async def test_postgres_optional_does_not_block_startup(self):
        """Postgres failure does not raise PreflightError."""
        config = _make_config(realestate_database_url="postgresql://u:p@localhost/missing")

        async def fake_optional(name, cfg, client, **_kwargs):
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


# ===========================================================================
# Qdrant preflight: both product collections ready before polling (#3202)
# ===========================================================================


class TestQdrantRemediationHint:
    """Qdrant remediation points at the idempotent demo bootstrap."""

    def test_qdrant_remediation_mentions_demo_bootstrap(self):
        from telegram_bot.preflight import _DEP_REMEDIATION

        assert "make demo-bootstrap" in _DEP_REMEDIATION["qdrant"].lower(), (
            "Qdrant remediation should mention 'make demo-bootstrap', "
            f"got: {_DEP_REMEDIATION['qdrant']}"
        )


class TestQdrantPreflightBothCollections:
    """Missing collections fail with actionable errors — no auto-create."""

    async def test_missing_knowledge_collection_fails_without_create(self):
        """A missing knowledge collection stops startup with remediation (#3202)."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists = AsyncMock(return_value=False)
        mock_qdrant.get_collection = AsyncMock()
        mock_qdrant.create_collection = AsyncMock()
        mock_qdrant.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        mock_qdrant.create_collection.assert_not_awaited()
        assert "does not exist" in failure_reasons["qdrant"]
        assert "make demo-bootstrap" in failure_reasons["qdrant"]

    async def test_missing_apartments_collection_fails_when_knowledge_ready(self):
        """Both product collections are enforced — apartments cannot be skipped."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        mock_qdrant = _ready_qdrant_client(exists=False)
        # Knowledge exists; apartments does not.
        exists_by_name = {"test_col": True, "apartments": False}

        async def _exists(collection: str) -> bool:
            return exists_by_name[collection]

        mock_qdrant.collection_exists = AsyncMock(side_effect=_exists)

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        assert "apartments" in failure_reasons["qdrant"]
        assert "does not exist" in failure_reasons["qdrant"]

    async def test_both_collections_ready_passes(self):
        """Startup passes only when both contracts hold."""
        config = _make_config()
        mock_qdrant_client = _ready_qdrant_client()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)

        assert result is True

    async def test_both_collections_failing_aggregates_reasons(self):
        """One failure report lists every actionable problem across collections."""
        config = _make_config()
        failure_reasons: dict[str, str] = {}
        mock_qdrant_client = _ready_qdrant_client(
            knowledge_info=_collection_info(points=0),
            apartments_info=_collection_info(
                points=0, payload_schema=_contract_payload_schema("apartments")
            ),
        )

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant_client):
            client = AsyncMock()
            result = await _check_single_dep(
                "qdrant", config, client, failure_reasons=failure_reasons
            )

        assert result is False
        reason = failure_reasons["qdrant"]
        assert "test_col" in reason
        assert "apartments" in reason
        assert reason.count("empty") >= 2

    async def test_non_404_exception_still_fails_without_create(self):
        """Connection-refused and other transport errors fail without any writes."""
        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists = AsyncMock(return_value=True)
        mock_qdrant.get_collection = AsyncMock(side_effect=Exception("Connection refused"))
        mock_qdrant.create_collection = AsyncMock()
        mock_qdrant.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)

        assert result is False
        mock_qdrant.create_collection.assert_not_awaited()


# ===========================================================================
# BGE-M3 URL guardrail (_validate_bge_m3_url)
# ===========================================================================


class TestBgeM3UrlGuardrail:
    """Guardrail validates BGE-M3 URLs before any network call."""

    def test_localhost_8000_passes(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://localhost:8000")
        assert ok is True
        assert err == ""

    def test_localhost_ipv4_8000_passes(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://127.0.0.1:8000")
        assert ok is True
        assert err == ""

    def test_localhost_ipv6_8000_passes(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://[::1]:8000")
        assert ok is True
        assert err == ""

    def test_container_host_bge_m3_8000_passes(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://bge-m3:8000")
        assert ok is True
        assert err == ""

    def test_container_host_bge_m3_wrong_port_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://bge-m3:8888")
        assert ok is False
        assert "8000" in err

    def test_container_host_bge_m3_no_port_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://bge-m3")
        assert ok is False
        assert "8000" in err

    def test_non_local_host_passes_any_port(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://embedding.example.com:9090")
        assert ok is True
        assert err == ""

    def test_localhost_8888_rejects_and_does_not_call_network(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("http://localhost:8888")
        assert ok is False
        assert "non-canonical port" in err or "port" in err.lower()

    def test_localhost_8080_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("http://localhost:8080")
        assert ok is False

    def test_ipv4_9000_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("http://127.0.0.1:9000")
        assert ok is False

    def test_ipv6_9999_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("http://[::1]:9999")
        assert ok is False

    def test_localhost_no_port_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("http://localhost")
        assert ok is False

    def test_valid_url_malformed_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("not-a-valid-url://")
        assert ok is False

    def test_empty_url_rejects(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("")
        assert ok is False

    def test_https_localhost_8000_passes(self):
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, err = _validate_bge_m3_url("https://localhost:8000")
        assert ok is True
        assert err == ""

    def test_localhost_abc_port_rejects_and_does_not_call_network(self):
        """Malformed port like 'http://localhost:abc' rejects without network call."""
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("http://localhost:abc")
        assert ok is False

    def test_localhost_99999_port_rejects_and_does_not_call_network(self):
        """Out-of-range port like 'http://localhost:99999' rejects without network call."""
        from telegram_bot.preflight import _validate_bge_m3_url

        ok, _err = _validate_bge_m3_url("http://localhost:99999")
        assert ok is False

    async def test_check_single_dep_rejects_localhost_8888_before_network(self):
        config = _make_config(bge_m3_url="http://localhost:8888")
        client = AsyncMock(spec=httpx.AsyncClient)

        result = await _check_single_dep("bge_m3", config, client)

        assert result is False
        client.get.assert_not_awaited()
        client.post.assert_not_awaited()

    async def test_check_single_dep_rejects_malformed_localhost_port_before_network(self):
        config = _make_config(bge_m3_url="http://localhost:abc")
        client = AsyncMock(spec=httpx.AsyncClient)

        result = await _check_single_dep("bge_m3", config, client)

        assert result is False
        client.get.assert_not_awaited()
        client.post.assert_not_awaited()

    async def test_check_single_dep_rejects_out_of_range_localhost_port_before_network(self):
        config = _make_config(bge_m3_url="http://localhost:99999")
        client = AsyncMock(spec=httpx.AsyncClient)

        result = await _check_single_dep("bge_m3", config, client)

        assert result is False
        client.get.assert_not_awaited()
        client.post.assert_not_awaited()
