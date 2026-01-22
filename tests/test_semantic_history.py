"""Test SemanticMessageHistory integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_cache_service_has_message_history():
    """CacheService should have message_history attribute."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")
    assert hasattr(service, "message_history"), "Missing message_history attribute"


@pytest.mark.asyncio
async def test_get_relevant_history():
    """get_relevant_history should return semantically relevant messages."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")

    mock_history = MagicMock()
    mock_history.aget_relevant = AsyncMock(
        return_value=[
            {"role": "user", "content": "квартира в Софии"},
            {"role": "assistant", "content": "Найдено 5 квартир в Софии"},
        ]
    )
    service.message_history = mock_history

    result = await service.get_relevant_history(user_id=123, query="апартаменты София", top_k=3)

    mock_history.aget_relevant.assert_called_once()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_add_semantic_message():
    """add_semantic_message should store message with embedding."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")

    mock_history = MagicMock()
    mock_history.aadd_message = AsyncMock()
    service.message_history = mock_history

    await service.add_semantic_message(user_id=123, role="user", content="тест")

    mock_history.aadd_message.assert_called_once()
