"""Tests for bot deep link handler — /start q_<uuid> flow."""

import json

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


@pytest.fixture
def mock_config(monkeypatch):
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("KOMMO_ACCESS_TOKEN", raising=False)
    return BotConfig(
        _env_file=None,
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        realestate_database_url="postgresql://postgres:postgres@127.0.0.1:1/realestate",
        rerank_provider="none",
    )


def _create_bot(mock_config):
    result: PropertyBot | None = None
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        result = PropertyBot(mock_config)
    assert result is not None
    return result


def _make_message(user_id=123, chat_id=123):
    msg = MagicMock()
    msg.from_user = MagicMock(id=user_id, first_name="Test")
    msg.chat = MagicMock(id=chat_id)
    msg.answer = AsyncMock()
    msg.model_copy = MagicMock(return_value=msg)
    msg.text = "/start q_test-uuid"
    return msg


@pytest.mark.asyncio
async def test_deeplink_expired_uuid(mock_config):
    """Expired/missing UUID should reply with 'link expired' message."""
    bot = _create_bot(mock_config)
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=None)
    bot._topic_manager = MagicMock()

    msg = _make_message()
    await bot._handle_deeplink_start(msg, "nonexistent-uuid")

    msg.answer.assert_called_once()
    assert "устарела" in msg.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_deeplink_invalid_json(mock_config):
    """Invalid JSON payload should reply with error."""
    bot = _create_bot(mock_config)
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value="not-json{{{")
    bot._topic_manager = MagicMock()

    msg = _make_message()
    await bot._handle_deeplink_start(msg, "test-uuid")

    msg.answer.assert_called_once()
    assert "ошибка" in msg.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_deeplink_unknown_expert(mock_config):
    """Unknown expert_id should reply with 'expert not found'."""
    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "nonexistent", "message": "hello"})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = MagicMock()

    msg = _make_message()
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": []},
    ):
        await bot._handle_deeplink_start(msg, "test-uuid")

    msg.answer.assert_called_once()
    assert "не найден" in msg.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_deeplink_success_creates_topic_and_triggers_rag(mock_config):
    """Valid deep link should create topic, echo message, and trigger RAG."""
    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "consultant", "message": "Подбери квартиру"})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = AsyncMock()
    bot._topic_manager.get_or_create_topic = AsyncMock(return_value=42)
    bot.bot = AsyncMock()
    bot.handle_query = AsyncMock()

    msg = _make_message()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": experts},
    ):
        await bot._handle_deeplink_start(msg, "test-uuid")

    # Topic created for the right expert
    bot._topic_manager.get_or_create_topic.assert_called_once_with(
        chat_id=msg.chat.id,
        expert_id="consultant",
        expert_name="Консультант",
        expert_emoji="👷",
    )
    # User message echoed in topic
    bot.bot.send_message.assert_called_once()
    send_kwargs = bot.bot.send_message.call_args.kwargs
    assert send_kwargs["message_thread_id"] == 42
    assert "Подбери квартиру" in send_kwargs["text"]
    # RAG pipeline triggered
    bot.handle_query.assert_called_once()


@pytest.mark.asyncio
async def test_deeplink_no_message_skips_rag(mock_config):
    """Deep link without message should create topic but not trigger RAG."""
    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "consultant", "message": ""})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = AsyncMock()
    bot._topic_manager.get_or_create_topic = AsyncMock(return_value=42)
    bot.bot = AsyncMock()
    bot.handle_query = AsyncMock()

    msg = _make_message()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": experts},
    ):
        await bot._handle_deeplink_start(msg, "test-uuid")

    # Topic created
    bot._topic_manager.get_or_create_topic.assert_called_once()
    # No message echo, no RAG
    bot.bot.send_message.assert_not_called()
    bot.handle_query.assert_not_called()


@pytest.mark.asyncio
async def test_deeplink_redis_deletes_key(mock_config):
    """Deep link should use atomic getdel (key consumed after read)."""
    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "consultant", "message": "test"})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = AsyncMock()
    bot._topic_manager.get_or_create_topic = AsyncMock(return_value=42)
    bot.bot = AsyncMock()
    bot.handle_query = AsyncMock()

    msg = _make_message()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": experts},
    ):
        await bot._handle_deeplink_start(msg, "test-uuid")

    bot._deeplink_redis.getdel.assert_called_once_with("miniapp:q:test-uuid")


@pytest.mark.asyncio
async def test_deeplink_topic_manager_none_skips(mock_config):
    """If TopicManager not initialized, deep link should silently return."""
    bot = _create_bot(mock_config)
    bot._deeplink_redis = None
    bot._topic_manager = None

    msg = _make_message()
    await bot._handle_deeplink_start(msg, "test-uuid")

    msg.answer.assert_not_called()


@pytest.mark.asyncio
async def test_deeplink_create_topic_error(mock_config):
    """TelegramBadRequest from create_forum_topic should be handled gracefully."""
    from aiogram.exceptions import TelegramBadRequest

    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "consultant", "message": "test"})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = AsyncMock()
    bot._topic_manager.get_or_create_topic = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: not enough rights")
    )

    msg = _make_message()
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": experts},
    ):
        await bot._handle_deeplink_start(msg, "test-uuid")

    msg.answer.assert_called_once()
    assert "не удалось" in msg.answer.call_args.args[0].lower()
