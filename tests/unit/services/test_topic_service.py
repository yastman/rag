from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.topic_service import TopicService


@pytest.fixture
def redis_mock():
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    return mock


@pytest.fixture
def service(redis_mock):
    return TopicService(redis=redis_mock)


@pytest.mark.asyncio
async def test_get_thread_id_returns_none_when_not_exists(service, redis_mock):
    redis_mock.get.return_value = None
    result = await service.get_thread_id(user_id=123, expert_id="consultant")
    assert result is None
    redis_mock.get.assert_called_once_with("topics:123:consultant")


@pytest.mark.asyncio
async def test_get_thread_id_returns_int(service, redis_mock):
    redis_mock.get.return_value = b"42"
    result = await service.get_thread_id(user_id=123, expert_id="consultant")
    assert result == 42


@pytest.mark.asyncio
async def test_save_thread_sets_both_keys(service, redis_mock):
    await service.save_thread(user_id=123, expert_id="consultant", thread_id=42)
    assert redis_mock.set.call_count == 2
    redis_mock.set.assert_any_call("topics:123:consultant", "42")
    redis_mock.set.assert_any_call("topics:123:thread:42", "consultant")


@pytest.mark.asyncio
async def test_get_expert_by_thread(service, redis_mock):
    redis_mock.get.return_value = b"investor"
    result = await service.get_expert_by_thread(user_id=123, thread_id=99)
    assert result == "investor"
    redis_mock.get.assert_called_once_with("topics:123:thread:99")


@pytest.mark.asyncio
async def test_get_expert_by_thread_returns_none(service, redis_mock):
    redis_mock.get.return_value = None
    result = await service.get_expert_by_thread(user_id=123, thread_id=99)
    assert result is None


@pytest.mark.asyncio
async def test_get_or_create_thread_existing(service, redis_mock):
    """Should return existing thread_id without calling bot."""
    redis_mock.get.return_value = b"42"
    bot_mock = AsyncMock()

    thread_id = await service.get_or_create_thread(
        bot=bot_mock,
        chat_id=123,
        user_id=123,
        expert_id="consultant",
        topic_name="👷 Консультант по недвижимости",
    )
    assert thread_id == 42
    bot_mock.create_forum_topic.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_thread_new(service, redis_mock):
    """Should create topic via bot API and save mapping."""
    redis_mock.get.return_value = None
    bot_mock = AsyncMock()
    forum_topic = AsyncMock()
    forum_topic.message_thread_id = 99
    bot_mock.create_forum_topic.return_value = forum_topic

    thread_id = await service.get_or_create_thread(
        bot=bot_mock,
        chat_id=123,
        user_id=123,
        expert_id="consultant",
        topic_name="👷 Консультант по недвижимости",
    )
    assert thread_id == 99
    bot_mock.create_forum_topic.assert_called_once_with(
        chat_id=123, name="👷 Консультант по недвижимости"
    )
    assert redis_mock.set.call_count == 2
