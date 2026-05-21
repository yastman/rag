"""Tests for checkpointer factory (memory.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import langgraph.checkpoint.redis.aio  # noqa: F401 — ensure submodule for patch()
from langgraph.checkpoint.memory import MemorySaver


class TestCreateRedisCheckpointer:
    def test_returns_instrumented_async_redis_saver(self):
        """create_redis_checkpointer wraps AsyncRedisSaver for direct timing."""
        from telegram_bot.integrations.memory import (
            InstrumentedCheckpointer,
            create_redis_checkpointer,
        )

        with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            result = create_redis_checkpointer("redis://localhost:6379")
            mock_cls.assert_called_once_with(redis_url="redis://localhost:6379")
            assert isinstance(result, InstrumentedCheckpointer)
            assert result._saver is mock_instance


class TestCheckpointerTTL:
    def test_redis_checkpointer_passes_ttl_dict(self):
        """create_redis_checkpointer passes SDK ttl config (minutes)."""
        from telegram_bot.integrations.memory import create_redis_checkpointer

        with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            result = create_redis_checkpointer(
                "redis://localhost:6379",
                ttl_minutes=10080,
                refresh_on_read=True,
            )

            mock_cls.assert_called_once_with(
                redis_url="redis://localhost:6379",
                ttl={"default_ttl": 10080, "refresh_on_read": True},
            )
            assert result._saver is mock_instance

    def test_redis_checkpointer_no_ttl_when_none(self):
        """create_redis_checkpointer omits ttl when ttl_minutes is None."""
        from telegram_bot.integrations.memory import create_redis_checkpointer

        with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            result = create_redis_checkpointer("redis://localhost:6379")

            mock_cls.assert_called_once_with(redis_url="redis://localhost:6379")
            assert result._saver is mock_instance


class TestAgentCheckpointerTTL:
    def test_agent_checkpointer_default_ttl(self):
        """create_redis_checkpointer with 120-minute TTL passes correct SDK kwargs."""
        from telegram_bot.integrations.memory import create_redis_checkpointer

        with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            result = create_redis_checkpointer(
                "redis://localhost:6379",
                ttl_minutes=120,
                refresh_on_read=True,
            )

            mock_cls.assert_called_once_with(
                redis_url="redis://localhost:6379",
                ttl={"default_ttl": 120, "refresh_on_read": True},
            )
            assert result._saver is mock_instance


class TestInstrumentedCheckpointer:
    def test_delegates_non_instrumented_attributes(self):
        """Wrapper preserves access to the underlying saver API surface."""
        from telegram_bot.integrations.memory import InstrumentedCheckpointer

        saver = Mock()
        saver.asetup = AsyncMock()
        wrapped = InstrumentedCheckpointer(saver)

        assert wrapped.asetup is saver.asetup

    async def test_does_not_record_when_capture_inactive(self):
        """Instrumented methods pass through without timing when capture is off."""
        from telegram_bot.integrations.memory import (
            InstrumentedCheckpointer,
            end_checkpoint_overhead_capture,
        )

        saver = Mock()
        saver.aput = AsyncMock(return_value="ok")
        wrapped = InstrumentedCheckpointer(saver)

        assert await wrapped.aput("config", "checkpoint", {}, {}) == "ok"

        saver.aput.assert_awaited_once_with("config", "checkpoint", {}, {})
        assert end_checkpoint_overhead_capture() is None

    async def test_records_instrumented_method_duration_when_capture_active(self):
        """Capture bucket records direct checkpoint call count and duration."""
        from telegram_bot.integrations.memory import (
            InstrumentedCheckpointer,
            begin_checkpoint_overhead_capture,
            end_checkpoint_overhead_capture,
            sum_checkpoint_overhead_ms,
        )

        saver = Mock()
        saver.aget_tuple = AsyncMock(return_value={"checkpoint": 1})
        wrapped = InstrumentedCheckpointer(saver)

        bucket = begin_checkpoint_overhead_capture()
        assert await wrapped.aget_tuple("config") == {"checkpoint": 1}
        result = end_checkpoint_overhead_capture()

        saver.aget_tuple.assert_awaited_once_with("config")
        assert result is bucket
        assert result is not None
        assert result["calls"] == 1.0
        assert result["aget_tuple_ms"] >= 0.0
        assert sum_checkpoint_overhead_ms(result) >= 0.0


class TestCreateFallbackCheckpointer:
    def test_returns_memory_saver(self):
        """create_fallback_checkpointer returns MemorySaver."""
        from telegram_bot.integrations.memory import create_fallback_checkpointer

        cp = create_fallback_checkpointer()
        assert isinstance(cp, MemorySaver)
