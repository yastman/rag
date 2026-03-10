"""Tests for bot deep link handler — /start q_<uuid> flow."""

import asyncio
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
async def test_pubsub_process_miniapp_start_no_message(mock_config):
    """Pub/sub path (no message) — expired UUID logs warning, no crash."""
    bot = _create_bot(mock_config)
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=None)
    bot._topic_manager = AsyncMock()

    # Pub/sub path: no message object
    await bot._process_miniapp_start(chat_id=123, uuid_str="expired-uuid")
    # Should not raise — just logs warning


@pytest.mark.asyncio
async def test_pubsub_success_calls_run_miniapp_rag(mock_config):
    """Pub/sub path calls _run_miniapp_rag instead of handle_query."""
    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "consultant", "message": "Подбери квартиру"})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = AsyncMock()
    bot._topic_manager.get_or_create_topic = AsyncMock(return_value=42)
    bot.bot = AsyncMock()
    bot._run_miniapp_rag = AsyncMock()
    bot.handle_query = AsyncMock()

    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": experts},
    ):
        await bot._process_miniapp_start(chat_id=123, uuid_str="test-uuid")

    # Pub/sub path → _run_miniapp_rag, NOT handle_query
    bot._run_miniapp_rag.assert_called_once_with(123, 42, "Подбери квартиру")
    bot.handle_query.assert_not_called()


@pytest.mark.asyncio
async def test_stale_topic_invalidate_and_recreate(mock_config):
    """Stale topic (deleted in Telegram) triggers invalidate + recreate."""
    from aiogram.exceptions import TelegramBadRequest

    bot = _create_bot(mock_config)
    payload = json.dumps({"expert_id": "consultant", "message": "test"})
    bot._deeplink_redis = AsyncMock()
    bot._deeplink_redis.getdel = AsyncMock(return_value=payload)
    bot._topic_manager = AsyncMock()
    # First call returns stale topic 42, second returns new topic 99
    bot._topic_manager.get_or_create_topic = AsyncMock(side_effect=[42, 99])
    bot._topic_manager.invalidate_topic = AsyncMock()
    bot.bot = AsyncMock()
    # First send_message raises (stale topic), second succeeds
    bot.bot.send_message = AsyncMock(
        side_effect=[TelegramBadRequest(method=MagicMock(), message="Bad Request"), None]
    )
    bot._run_miniapp_rag = AsyncMock()

    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    with patch(
        "telegram_bot.services.content_loader.load_mini_app_config",
        return_value={"experts": experts},
    ):
        await bot._process_miniapp_start(chat_id=123, uuid_str="test-uuid")

    # Topic invalidated and recreated
    bot._topic_manager.invalidate_topic.assert_called_once_with(123, "consultant")
    assert bot._topic_manager.get_or_create_topic.call_count == 2
    # RAG called with new topic
    bot._run_miniapp_rag.assert_called_once_with(123, 99, "test")


@pytest.mark.asyncio
async def test_run_miniapp_rag_success(mock_config):
    """_run_miniapp_rag sends RAG response to topic thread."""
    bot = _create_bot(mock_config)
    bot.bot = AsyncMock()

    with (
        patch(
            "telegram_bot.agents.rag_pipeline.rag_pipeline",
            new_callable=AsyncMock,
            return_value={"documents": [{"text": "doc1"}]},
        ),
        patch(
            "telegram_bot.services.generate_response.generate_response",
            new_callable=AsyncMock,
            return_value={"response": "Ответ от RAG"},
        ),
    ):
        await bot._run_miniapp_rag(chat_id=123, topic_id=42, user_message="тест")

    # Answer sent to correct topic thread
    bot.bot.send_message.assert_called_once()
    call_kwargs = bot.bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 123
    assert call_kwargs["message_thread_id"] == 42
    assert call_kwargs["text"] == "Ответ от RAG"


@pytest.mark.asyncio
async def test_run_miniapp_rag_error_sends_fallback(mock_config):
    """_run_miniapp_rag sends fallback message on pipeline error."""
    bot = _create_bot(mock_config)
    bot.bot = AsyncMock()

    with patch(
        "telegram_bot.agents.rag_pipeline.rag_pipeline",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Pipeline crashed"),
    ):
        await bot._run_miniapp_rag(chat_id=123, topic_id=42, user_message="тест")

    bot.bot.send_message.assert_called_once()
    assert "ошибка" in bot.bot.send_message.call_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_run_miniapp_rag_no_documents(mock_config):
    """_run_miniapp_rag sends 'not found' when no documents retrieved."""
    bot = _create_bot(mock_config)
    bot.bot = AsyncMock()

    with patch(
        "telegram_bot.agents.rag_pipeline.rag_pipeline",
        new_callable=AsyncMock,
        return_value={"documents": []},
    ):
        await bot._run_miniapp_rag(chat_id=123, topic_id=42, user_message="тест")

    bot.bot.send_message.assert_called_once()
    assert "не нашёл" in bot.bot.send_message.call_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_subscriber_not_started_without_topic_manager(mock_config):
    """Pub/sub subscriber not started when _topic_manager is None (feature disabled)."""
    bot = _create_bot(mock_config)
    bot._topic_manager = None
    bot._deeplink_redis = None
    bot._miniapp_subscriber_task = None

    # _process_miniapp_start should silently return
    await bot._process_miniapp_start(chat_id=123, uuid_str="test-uuid")
    # No crash, no task created
    assert bot._miniapp_subscriber_task is None


def _make_mock_pubsub(listen_fn):
    """Create a mock pubsub with sync pubsub() and async subscribe/unsubscribe."""
    mock_pubsub = MagicMock()
    mock_pubsub.listen = listen_fn
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_redis.aclose = AsyncMock()
    return mock_redis, mock_pubsub


@pytest.mark.asyncio
async def test_subscriber_loop_invalid_message(mock_config):
    """Subscriber loop skips invalid JSON messages without crashing."""
    bot = _create_bot(mock_config)
    bot._deeplink_redis = AsyncMock()
    bot._topic_manager = AsyncMock()
    bot._process_miniapp_start = AsyncMock()

    async def mock_listen():
        yield {"type": "subscribe", "data": None}  # subscription confirmation
        yield {"type": "message", "data": "not-valid-json{{{"}  # invalid
        yield {"type": "message", "data": json.dumps({"uuid": "abc", "user_id": 123})}
        raise asyncio.CancelledError  # stop loop

    mock_redis, _mock_pubsub = _make_mock_pubsub(mock_listen)

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        await bot._miniapp_subscriber_loop()

    # Only valid message processed
    bot._process_miniapp_start.assert_called_once_with(chat_id=123, uuid_str="abc")


@pytest.mark.asyncio
async def test_subscriber_loop_crash_logged(mock_config):
    """Subscriber loop logs exception on unexpected crash and cleans up."""
    bot = _create_bot(mock_config)

    async def mock_listen():
        raise ConnectionError("Redis gone")
        yield  # make it a generator

    mock_redis, mock_pubsub = _make_mock_pubsub(mock_listen)

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        # Should not raise — exception caught and logged
        await bot._miniapp_subscriber_loop()

    # Cleanup called
    mock_pubsub.unsubscribe.assert_called_once_with("miniapp:start")
    mock_redis.aclose.assert_called_once()


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
