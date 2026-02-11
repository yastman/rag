"""Tests for checkpointer factory (memory.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


class TestCreateFallbackCheckpointer:
    def test_returns_memory_saver(self):
        """create_fallback_checkpointer returns MemorySaver."""
        from telegram_bot.integrations.memory import create_fallback_checkpointer

        cp = create_fallback_checkpointer()
        assert isinstance(cp, MemorySaver)
