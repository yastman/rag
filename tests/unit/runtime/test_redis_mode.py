"""Redis mode policy table tests (#3362, decision #3354).

The single public ``REDIS_MODE`` contract lives in
``src.runtime.integrations.redis_mode``. Consumers receive the typed
enum/policy and never reparse strings.

Decision table (issue #3354):

| Mode            | Connection/cache                       | Durable capabilities        | Polling ownership                |
|-----------------|----------------------------------------|-----------------------------|----------------------------------|
| disabled        | no Redis import/client/DNS/socket      | unavailable, never memory   | one process, no lock claim       |
| single_instance | connect when configured; fail open     | only while connected        | one process, no lock claim       |
| multi_instance  | Redis required at startup              | required                    | distributed lock required        |
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.runtime.integrations.redis_mode import (
    REDIS_MODE_POLICIES,
    RedisCapability,
    RedisMode,
    RedisModeConfigError,
    RedisModePolicy,
    parse_redis_mode,
    redis_mode_policy,
    validate_redis_mode,
)


REPO_ROOT = Path(__file__).parents[3]


class TestPolicyTable:
    """The one policy table — every mode has exactly one row."""

    def test_table_covers_all_modes(self) -> None:
        assert set(REDIS_MODE_POLICIES) == set(RedisMode)

    def test_disabled_mode_forbids_clients_and_locks(self) -> None:
        policy = redis_mode_policy(RedisMode.DISABLED)
        assert policy.allows_client is False
        assert policy.requires_connection_before_polling is False
        assert policy.polling_lock_required is False
        assert policy.durable_capabilities_allowed is False
        assert policy.cache_fail_open is False

    def test_single_instance_connects_without_lock_claim(self) -> None:
        policy = redis_mode_policy(RedisMode.SINGLE_INSTANCE)
        assert policy.allows_client is True
        assert policy.requires_connection_before_polling is False
        assert policy.polling_lock_required is False
        assert policy.durable_capabilities_allowed is True
        assert policy.cache_fail_open is True

    def test_multi_instance_requires_connection_and_lock(self) -> None:
        policy = redis_mode_policy(RedisMode.MULTI_INSTANCE)
        assert policy.allows_client is True
        assert policy.requires_connection_before_polling is True
        assert policy.polling_lock_required is True
        assert policy.durable_capabilities_allowed is True

    def test_policies_are_immutable(self) -> None:
        for policy in REDIS_MODE_POLICIES.values():
            assert isinstance(policy, RedisModePolicy)
            with pytest.raises(Exception):  # noqa: B017 — frozen dataclass raises FrozenInstanceError
                policy.mode = RedisMode.DISABLED  # type: ignore[misc]

    def test_capability_states_distinguish_enabled_degraded_disabled(self) -> None:
        assert {c.value for c in RedisCapability} == {"enabled", "degraded", "disabled"}


class TestParseRedisMode:
    """Single parse point — consumers never reparse strings."""

    def test_enum_passthrough(self) -> None:
        assert parse_redis_mode(RedisMode.MULTI_INSTANCE) is RedisMode.MULTI_INSTANCE

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("disabled", RedisMode.DISABLED),
            ("single_instance", RedisMode.SINGLE_INSTANCE),
            ("multi_instance", RedisMode.MULTI_INSTANCE),
            ("SINGLE_INSTANCE", RedisMode.SINGLE_INSTANCE),
            ("  multi_instance  ", RedisMode.MULTI_INSTANCE),
        ],
    )
    def test_valid_strings(self, raw: str, expected: RedisMode) -> None:
        assert parse_redis_mode(raw) is expected

    @pytest.mark.parametrize("raw", [None, ""])
    def test_unset_defaults_to_disabled(self, raw: str | None) -> None:
        # "Defaults: reusable core disabled" (decision #3354).
        assert parse_redis_mode(raw) is RedisMode.DISABLED

    def test_invalid_value_raises_with_valid_values(self) -> None:
        with pytest.raises(RedisModeConfigError) as exc_info:
            parse_redis_mode("clustered")
        message = str(exc_info.value)
        assert "clustered" in message
        for valid in ("disabled", "single_instance", "multi_instance"):
            assert valid in message

    def test_error_is_value_error(self) -> None:
        assert issubclass(RedisModeConfigError, ValueError)


class TestValidateRedisMode:
    """Configuration invariants from decision #3354."""

    def test_multi_instance_requires_nonempty_url(self) -> None:
        with pytest.raises(RedisModeConfigError, match="multi_instance"):
            validate_redis_mode(
                RedisMode.MULTI_INSTANCE, redis_url="", redis_only_feature_enabled=False
            )
        with pytest.raises(RedisModeConfigError, match="multi_instance"):
            validate_redis_mode(
                RedisMode.MULTI_INSTANCE, redis_url="   ", redis_only_feature_enabled=False
            )

    def test_disabled_with_explicit_redis_only_feature_is_configuration_error(self) -> None:
        with pytest.raises(RedisModeConfigError, match="HANDOFF_ENABLED"):
            validate_redis_mode(
                RedisMode.DISABLED,
                redis_url="redis://localhost:6379",
                redis_only_feature_enabled=True,
            )

    @pytest.mark.parametrize(
        ("mode", "url", "feature"),
        [
            (RedisMode.DISABLED, "redis://localhost:6379", False),
            (RedisMode.SINGLE_INSTANCE, "redis://localhost:6379", True),
            (RedisMode.SINGLE_INSTANCE, "redis://localhost:6379", False),
            (RedisMode.MULTI_INSTANCE, "redis://redis:6379", True),
        ],
    )
    def test_valid_combinations_pass(self, mode: RedisMode, url: str, feature: bool) -> None:
        # No exception raised.
        validate_redis_mode(mode, redis_url=url, redis_only_feature_enabled=feature)


class TestGraphConfigRedisMode:
    """GraphConfig carries the typed mode ("reusable core disabled")."""

    def test_default_is_disabled(self) -> None:
        from src.runtime.config import GraphConfig

        assert GraphConfig().redis_mode is RedisMode.DISABLED

    def test_from_env_reads_redis_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.runtime.config import GraphConfig

        monkeypatch.setenv("REDIS_MODE", "multi_instance")
        config = GraphConfig.from_env()
        assert config.redis_mode is RedisMode.MULTI_INSTANCE

    def test_from_env_invalid_mode_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.runtime.config import GraphConfig

        monkeypatch.setenv("REDIS_MODE", "clustered")
        with pytest.raises(RedisModeConfigError):
            GraphConfig.from_env()

    def test_flat_kwarg_accepted(self) -> None:
        from src.runtime.config import GraphConfig

        config = GraphConfig(redis_mode=RedisMode.SINGLE_INSTANCE)
        assert config.redis_mode is RedisMode.SINGLE_INSTANCE


class TestImportIsolation:
    """Disabled mode must run with the redis client packages absent."""

    def test_redis_mode_module_imports_without_redis(self) -> None:
        code = (
            "import sys\n"
            "sys.modules['redis'] = None\n"
            "sys.modules['redis.asyncio'] = None\n"
            "sys.modules['redisvl'] = None\n"
            "from src.runtime.integrations.redis_mode import RedisMode\n"
            "assert RedisMode.DISABLED.value == 'disabled'\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"stderr:\n{result.stderr}"
        assert "OK" in result.stdout
