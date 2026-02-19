"""Tests for checkpointer factory (memory.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import langgraph.checkpoint.redis.aio  # noqa: F401 — ensure submodule for patch()
from langgraph.checkpoint.memory import MemorySaver


class TestCreateRedisCheckpointer:
    def test_returns_async_redis_saver(self):
        """create_redis_checkpointer returns AsyncRedisSaver instance."""
        from telegram_bot.integrations.memory import create_redis_checkpointer

        with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            result = create_redis_checkpointer("redis://localhost:6379")
            mock_cls.assert_called_once_with(redis_url="redis://localhost:6379")
            assert result is mock_instance


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
            assert result is mock_instance

    def test_redis_checkpointer_no_ttl_when_none(self):
        """create_redis_checkpointer omits ttl when ttl_minutes is None."""
        from telegram_bot.integrations.memory import create_redis_checkpointer

        with patch("langgraph.checkpoint.redis.aio.AsyncRedisSaver") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            result = create_redis_checkpointer("redis://localhost:6379")

            mock_cls.assert_called_once_with(redis_url="redis://localhost:6379")
            assert result is mock_instance


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
            assert result is mock_instance


class TestCreateFallbackCheckpointer:
    def test_returns_memory_saver(self):
        """create_fallback_checkpointer returns MemorySaver."""
        from telegram_bot.integrations.memory import create_fallback_checkpointer

        cp = create_fallback_checkpointer()
        assert isinstance(cp, MemorySaver)
