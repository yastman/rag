"""Unit tests for the local bot health-check helper."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import AuthenticationError


class TestResolveRedisUrls:
    def test_resolve_redis_urls_prefers_authenticated_url(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("REDIS_PASSWORD", "dev_redis_pass")

        from scripts.test_bot_health import resolve_redis_urls

        assert resolve_redis_urls()[0] == "redis://:dev_redis_pass@localhost:6379"

    def test_resolve_redis_urls_keeps_explicit_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://:secret@localhost:6379/0")

        from scripts.test_bot_health import resolve_redis_urls

        assert resolve_redis_urls() == ["redis://:secret@localhost:6379/0"]


class TestCheckRedis:
    @pytest.mark.asyncio
    async def test_check_redis_falls_through_auth_error(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("REDIS_PASSWORD", "dev_redis_pass")

        from scripts import test_bot_health as subject

        bad_client = AsyncMock()
        bad_client.ping = AsyncMock(side_effect=AuthenticationError("bad auth"))
        bad_client.aclose = AsyncMock()

        good_client = AsyncMock()
        good_client.ping = AsyncMock(return_value=True)
        good_client.aclose = AsyncMock()

        clients = [bad_client, good_client]

        def fake_from_url(url, decode_responses=True):
            return clients.pop(0)

        monkeypatch.setattr(subject.redis, "from_url", fake_from_url)

        ok, message = await subject.check_redis()

        assert ok is True
        assert "Redis OK" in message
        bad_client.aclose.assert_awaited_once()
        good_client.aclose.assert_awaited_once()
