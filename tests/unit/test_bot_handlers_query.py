"""Unit tests for bot query/voice handler edge cases (#1250 recursion limit)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


@pytest.fixture
def mock_config(monkeypatch):
    """Create mock bot config."""
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
    """Create PropertyBot with all deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(mock_config)


def _make_voice_message():
    """Create a mock voice message."""
    message = MagicMock()
    message.from_user = MagicMock(id=12345)
    message.chat = MagicMock(id=12345)
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.bot.get_file = AsyncMock()
    message.bot.download_file = AsyncMock()
    message.answer = AsyncMock()
    message.voice = MagicMock()
    message.voice.file_id = "file123"
    message.voice.duration = 5
    file_mock = MagicMock()
    file_mock.file_path = "voice/file.ogg"
    message.bot.get_file.return_value = file_mock
    return message


def _make_typing_cm():
    """Create a mock ChatActionSender.typing() context manager."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock()
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


class TestHandleVoiceRecursionLimit:
    """Test handle_voice GraphRecursionError handling — #1250."""

    async def test_recursion_limit_sends_graceful_message(self, mock_config):
        """GraphRecursionError should send a graceful 'limit reached' message."""
        bot = _create_bot(mock_config)

        from langgraph.errors import GraphRecursionError

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=GraphRecursionError("recursion limit exceeded"))

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot._write_voice_error_scores") as mock_error_scores,
        ):
            message = _make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

        # User should receive graceful limit-reached message, not generic error
        message.answer.assert_called()
        limit_msg_sent = any(
            "лимит" in str(call).lower() or "limit" in str(call).lower()
            for call in message.answer.call_args_list
        )
        assert limit_msg_sent, "Expected graceful recursion-limit message to user"

        # Error scores should be written with recursion_limit reason
        mock_error_scores.assert_called_once()
        call_kwargs = mock_error_scores.call_args.kwargs
        assert call_kwargs.get("error_reason") == "recursion_limit"
        assert call_kwargs.get("voice_duration_s") == 5

        # write_langfuse_scores should NOT be called because there is no result state
        mock_write_scores.assert_not_called()

    async def test_recursion_limit_logs_with_session_context(self, mock_config, caplog):
        """GraphRecursionError should be logged with session/user context."""
        bot = _create_bot(mock_config)

        from langgraph.errors import GraphRecursionError

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=GraphRecursionError("recursion limit exceeded"))

        caplog.set_level("INFO")
        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot._write_voice_error_scores"),
        ):
            message = _make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

        # Log should contain user/session context for observability
        assert any(
            "recursion" in record.message.lower() or "limit" in record.message.lower()
            for record in caplog.records
        ), "Expected log mention of recursion limit"


class TestClientDirectIntentPrecheck:
    """Regression tests for client-direct pre-agent intent detection (#1369)."""

    async def test_pre_agent_intent_check_does_not_call_traced_detector(self, mock_config):
        """PropertyBot precheck must avoid creating extra detect-agent-intent spans."""
        bot = _create_bot(mock_config)
        message = MagicMock()

        with (
            patch(
                "telegram_bot.pipelines.client.detect_agent_intent",
                side_effect=AssertionError(
                    "traced detect_agent_intent must not run in bot precheck"
                ),
            ),
            patch(
                "telegram_bot.pipelines.client.run_client_pipeline",
                AsyncMock(return_value=SimpleNamespace(needs_agent=False, answer="ok")),
            ) as mock_run_pipeline,
        ):
            result = await bot._handle_client_direct_pipeline(
                message=message,
                user_text="какие документы нужны",
                user_id=123,
                session_id="s1",
                role="client",
                query_type="GENERAL",
                rag_result_store={},
            )

        assert result == "ok"
        assert mock_run_pipeline.await_count == 1
