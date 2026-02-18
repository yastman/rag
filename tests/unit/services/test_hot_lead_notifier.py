"""Tests for hot lead notification service (#388)."""

from unittest.mock import AsyncMock

from telegram_bot.services.hot_lead_notifier import HotLeadNotifier


async def test_notifier_sends_once_per_session():
    """Fan-out to managers on first event; dedupe skips second."""
    cache = AsyncMock()
    cache.redis = AsyncMock()
    cache.redis.set = AsyncMock(side_effect=[True, False])
    bot = AsyncMock()

    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1, 2], dedupe_ttl_sec=3600)
    payload = {"lead_id": 77, "score": 88, "session_id": "chat-abc"}

    await notifier.notify_if_hot(payload)
    await notifier.notify_if_hot(payload)

    # First call fans out to 2 managers, second is deduped
    assert bot.send_message.await_count == 2


async def test_notifier_returns_false_when_deduped():
    """Return False when lead notification was already sent."""
    cache = AsyncMock()
    cache.redis = AsyncMock()
    cache.redis.set = AsyncMock(return_value=False)
    bot = AsyncMock()

    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=3600)
    result = await notifier.notify_if_hot({"lead_id": 1, "score": 90, "session_id": "s1"})

    assert result is False
    bot.send_message.assert_not_awaited()


async def test_notifier_returns_false_on_missing_fields():
    """Return False when required fields are missing."""
    cache = AsyncMock()
    bot = AsyncMock()

    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=3600)
    result = await notifier.notify_if_hot({"score": 90})

    assert result is False
    bot.send_message.assert_not_awaited()


async def test_notifier_handles_non_numeric_score_without_crashing():
    """Invalid score payload should not crash notification flow."""
    cache = AsyncMock()
    cache.redis = None
    bot = AsyncMock()
    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=3600)

    result = await notifier.notify_if_hot({"lead_id": 1, "score": "high", "session_id": "s1"})

    assert result is True
    bot.send_message.assert_awaited_once()
    assert "score=0" in bot.send_message.await_args.kwargs["text"]
