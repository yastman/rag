"""BotConfig REDIS_MODE field tests (#3362, decision #3354).

BotConfig carries the typed ``RedisMode`` value; the default is
``disabled`` ("reusable core disabled") and Compose overrides it to
``single_instance`` explicitly.
"""

from __future__ import annotations

import pytest

from src.runtime.integrations.redis_mode import RedisMode
from tests.unit._bot_config_factory import make_bot_config


class TestBotConfigRedisMode:
    def test_default_mode_is_disabled(self) -> None:
        config = make_bot_config()
        assert config.redis_mode is RedisMode.DISABLED

    def test_redis_mode_is_typed_enum(self) -> None:
        config = make_bot_config(redis_mode="single_instance")
        assert isinstance(config.redis_mode, RedisMode)
        assert config.redis_mode is RedisMode.SINGLE_INSTANCE

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("disabled", RedisMode.DISABLED),
            ("multi_instance", RedisMode.MULTI_INSTANCE),
            ("SINGLE_INSTANCE", RedisMode.SINGLE_INSTANCE),
        ],
    )
    def test_mode_strings_parse(self, raw: str, expected: RedisMode) -> None:
        assert make_bot_config(redis_mode=raw).redis_mode is expected

    def test_invalid_mode_rejected_with_valid_values(self) -> None:
        with pytest.raises(ValueError, match="single_instance"):
            make_bot_config(redis_mode="clustered")


class TestBotConfigRedisModeInvariants:
    """Configuration errors surface before polling starts (model validation)."""

    def test_disabled_with_handoff_enabled_is_rejected(self) -> None:
        # Handoff state is a Redis-only durable feature: disabled mode plus an
        # explicitly enabled durable feature is a configuration error (#3354).
        with pytest.raises(ValueError, match="REDIS_MODE=disabled"):
            make_bot_config(
                redis_mode="disabled",
                handoff_enabled=True,
                managers_group_id=-100123,
            )

    def test_multi_instance_with_empty_redis_url_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="multi_instance"):
            make_bot_config(redis_mode="multi_instance", redis_url="")

    def test_multi_instance_with_url_accepted(self) -> None:
        config = make_bot_config(redis_mode="multi_instance", redis_url="redis://redis:6379")
        assert config.redis_mode is RedisMode.MULTI_INSTANCE

    def test_single_instance_with_handoff_accepted(self) -> None:
        config = make_bot_config(
            redis_mode="single_instance",
            handoff_enabled=True,
            managers_group_id=-100123,
        )
        assert config.redis_mode is RedisMode.SINGLE_INSTANCE

    def test_disabled_ignores_present_redis_url_without_error(self) -> None:
        # "A present Redis URL/password in disabled mode triggers no import or
        # connection" — it must not be an error either.
        config = make_bot_config(redis_mode="disabled", redis_url="redis://localhost:6379")
        assert config.redis_mode is RedisMode.DISABLED
