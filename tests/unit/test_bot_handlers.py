"""Unit tests for telegram_bot/bot.py handlers (LangGraph pipeline)."""

import pytest


# Skip entire module if aiogram not installed
pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot, make_session_id
from telegram_bot.config import BotConfig


@pytest.fixture
def mock_config():
    """Create mock bot config."""
    return BotConfig(
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
    )


# Patches needed for PropertyBot.__init__
BOT_INIT_PATCHES = [
    "telegram_bot.bot.Bot",
    "telegram_bot.integrations.cache.CacheLayerManager",
    "telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings",
    "telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings",
    "telegram_bot.services.qdrant.QdrantService",
    "telegram_bot.graph.config.GraphConfig.create_llm",
]


def _create_bot(mock_config):
    """Create PropertyBot with all deps mocked. Returns (bot, patches_dict)."""
    patches = {}
    with (
        patch("telegram_bot.bot.Bot") as mock_bot,
        patch("telegram_bot.integrations.cache.CacheLayerManager") as mock_cache,
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings") as mock_emb,
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings") as mock_sparse,
        patch("telegram_bot.services.qdrant.QdrantService") as mock_qdrant,
        patch("telegram_bot.graph.config.GraphConfig.create_llm") as mock_llm,
    ):
        patches = {
            "bot": mock_bot,
            "cache": mock_cache,
            "embeddings": mock_emb,
            "sparse": mock_sparse,
            "qdrant": mock_qdrant,
            "llm": mock_llm,
        }
        bot = PropertyBot(mock_config)
    return bot, patches


class TestPropertyBotInit:
    """Test PropertyBot initialization."""

    def test_init_creates_services(self, mock_config):
        """Test that initialization creates all services."""
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.integrations.cache.CacheLayerManager") as mock_cache,
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings") as mock_emb,
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings") as mock_sparse,
            patch("telegram_bot.services.qdrant.QdrantService") as mock_qdrant,
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        ):
            bot = PropertyBot(mock_config)

            assert bot.config == mock_config
            mock_cache.assert_called_once()
            mock_emb.assert_called_once()
            mock_sparse.assert_called_once()
            mock_qdrant.assert_called_once()

    def test_init_passes_qdrant_timeout(self, mock_config):
        """PropertyBot should pass configured timeout to QdrantService."""
        mock_config.qdrant_timeout = 7
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.integrations.cache.CacheLayerManager"),
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
            patch("telegram_bot.services.qdrant.QdrantService") as mock_qdrant,
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        ):
            PropertyBot(mock_config)

        assert mock_qdrant.call_args.kwargs["timeout"] == 7


class TestCommandHandlers:
    """Test command handlers."""

    @pytest.mark.asyncio
    async def test_cmd_start(self, mock_config):
        """Test /start command handler."""
        bot, _ = _create_bot(mock_config)

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_start(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Привет" in call_args
        assert "недвижимость" in call_args

    @pytest.mark.asyncio
    async def test_cmd_help(self, mock_config):
        """Test /help command handler."""
        bot, _ = _create_bot(mock_config)

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_help(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Примеры запросов" in call_args
        assert "/clear" in call_args
        assert "/stats" in call_args

    @pytest.mark.asyncio
    async def test_cmd_clear(self, mock_config):
        """Test /clear command handler."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()

        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = 12345
        message.answer = AsyncMock()

        await bot.cmd_clear(message)

        bot._cache.clear_conversation.assert_called_once_with(12345)
        message.answer.assert_called_once()
        assert "очищена" in message.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_cmd_clear_uses_checkpointer_delete_thread(self, mock_config):
        """Test /clear calls checkpointer.adelete_thread for SDK-native cleanup."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        bot._checkpointer = AsyncMock()

        message = MagicMock()
        message.from_user = MagicMock(id=12345)
        message.answer = AsyncMock()

        await bot.cmd_clear(message)

        bot._checkpointer.adelete_thread.assert_awaited_once_with("12345")
        bot._cache.clear_conversation.assert_awaited_once_with(12345)

    @pytest.mark.asyncio
    async def test_cmd_clear_handles_no_checkpointer(self, mock_config):
        """Test /clear works when checkpointer is None (fallback)."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        bot._checkpointer = None

        message = MagicMock()
        message.from_user = MagicMock(id=12345)
        message.answer = AsyncMock()

        await bot.cmd_clear(message)

        bot._cache.clear_conversation.assert_awaited_once_with(12345)
        message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_clear_reports_partial_failure_on_checkpointer_error(self, mock_config):
        """Test /clear reports partial failure when checkpointer deletion fails."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        bot._checkpointer = AsyncMock()
        bot._checkpointer.adelete_thread = AsyncMock(side_effect=RuntimeError("redis down"))

        message = MagicMock()
        message.from_user = MagicMock(id=12345)
        message.answer = AsyncMock()

        await bot.cmd_clear(message)

        bot._cache.clear_conversation.assert_awaited_once_with(12345)
        bot._checkpointer.adelete_thread.assert_awaited_once_with("12345")
        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args.args[0]
        assert "частично" in answer_text.lower()

    @pytest.mark.asyncio
    async def test_cmd_stats(self, mock_config):
        """Test /stats command handler."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.get_metrics.return_value = {
            "semantic": {"hit_rate": 80.0, "hits": 40, "total": 50},
            "embeddings": {"hit_rate": 70.0, "hits": 35, "total": 50},
        }

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_stats(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Статистика" in call_args
        assert "80" in call_args

    @pytest.mark.asyncio
    async def test_cmd_stats_uses_hits_plus_misses_denominator(self, mock_config):
        """Test /stats command uses hits + misses as denominator (not 'total')."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.get_metrics.return_value = {
            "semantic": {"hit_rate": 75.0, "hits": 30, "misses": 10},
        }

        message = MagicMock()
        message.answer = AsyncMock()

        await bot.cmd_stats(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        # Should show "30/40" (hits/total), where total = hits + misses
        assert "30/40" in call_args, "Expected denominator to be hits + misses = 40"

    @pytest.mark.asyncio
    async def test_cmd_metrics(self, mock_config):
        """Test /metrics command handler."""
        bot, _ = _create_bot(mock_config)

        message = MagicMock()
        message.answer = AsyncMock()

        with patch("telegram_bot.bot.PipelineMetrics") as mock_pm:
            mock_metrics = MagicMock()
            mock_metrics.format_text.return_value = "p50=100ms p95=200ms"
            mock_pm.get.return_value = mock_metrics

            await bot.cmd_metrics(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "p50" in call_args


class TestHandleQuery:
    """Test handle_query method - LangGraph pipeline."""

    @pytest.mark.asyncio
    async def test_handle_query_invokes_graph(self, mock_config):
        """Test that handle_query builds and invokes the graph."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok", "query_type": "GENERAL"})

        with patch("telegram_bot.bot.build_graph", return_value=mock_graph):
            message = MagicMock()
            message.text = "квартиры в Несебр"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            # Mock ChatActionSender.typing context manager
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            mock_graph.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_query_sends_typing(self, mock_config):
        """Test that typing action is sent early."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok"})

        with patch("telegram_bot.bot.build_graph", return_value=mock_graph):
            message = MagicMock()
            message.text = "test"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            message.bot.send_chat_action.assert_called_once_with(chat_id=12345, action="typing")

    @pytest.mark.asyncio
    async def test_handle_query_writes_langfuse_trace(self, mock_config):
        """Test that handle_query updates Langfuse trace and writes scores."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"response": "ok", "query_type": "GENERAL", "latency_stages": {}}
        )
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = MagicMock()
            message.text = "test"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            mock_lf.update_current_trace.assert_called_once()
            mock_write_scores.assert_called_once_with(mock_lf, mock_graph.ainvoke.return_value)

    @pytest.mark.asyncio
    async def test_handle_query_passes_state_to_graph(self, mock_config):
        """Test that handle_query passes correct initial state to graph."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"response": "ok", "query_type": "GENERAL", "latency_stages": {}}
        )

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = MagicMock()
            message.text = "квартиры"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            state_arg = mock_graph.ainvoke.call_args[0][0]
            assert state_arg["user_id"] == 12345
            assert "квартиры" in str(state_arg["messages"])

    @pytest.mark.asyncio
    async def test_handle_query_passes_max_rewrite_attempts(self, mock_config):
        """Test that handle_query sets max_rewrite_attempts from graph config."""
        bot, _ = _create_bot(mock_config)
        bot._graph_config.max_rewrite_attempts = 3

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"response": "ok", "query_type": "GENERAL"})

        with patch("telegram_bot.bot.build_graph", return_value=mock_graph):
            message = MagicMock()
            message.text = "квартиры"
            message.from_user = MagicMock()
            message.from_user.id = 12345
            message.chat = MagicMock()
            message.chat.id = 12345
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            state_arg = mock_graph.ainvoke.call_args[0][0]
            assert state_arg["max_rewrite_attempts"] == 3


class TestCheckpointNamespace:
    """Test checkpoint namespace separation for text/voice."""

    @pytest.mark.asyncio
    async def test_handle_query_passes_text_checkpoint_ns(self, mock_config):
        """handle_query passes checkpoint_ns='tg:text:v1' in invoke_config."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"response": "ok", "query_type": "GENERAL", "latency_stages": {}}
        )

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = MagicMock()
            message.text = "test"
            message.from_user = MagicMock(id=12345)
            message.chat = MagicMock(id=12345)
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_query(message)

            cfg = mock_graph.ainvoke.call_args.kwargs["config"]["configurable"]
            assert cfg["thread_id"] == "12345"
            assert cfg["checkpoint_ns"] == "tg:text:v1"

    @pytest.mark.asyncio
    async def test_handle_voice_passes_voice_checkpoint_ns(self, mock_config):
        """handle_voice passes checkpoint_ns='tg:voice:v1' in invoke_config."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "response": "ok",
                "query_type": "GENERAL",
                "latency_stages": {},
                "stt_text": "test",
            }
        )

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = MagicMock()
            message.from_user = MagicMock(id=12345)
            message.chat = MagicMock(id=12345)
            message.bot = MagicMock()
            message.bot.send_chat_action = AsyncMock()
            message.bot.get_file = AsyncMock()
            message.bot.download_file = AsyncMock()
            message.voice = MagicMock()
            message.voice.file_id = "file123"
            message.voice.duration = 5
            file_mock = MagicMock()
            file_mock.file_path = "voice/file.ogg"
            message.bot.get_file.return_value = file_mock

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock()
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            cfg = mock_graph.ainvoke.call_args.kwargs["config"]["configurable"]
            assert cfg["thread_id"] == "12345"
            assert cfg["checkpoint_ns"] == "tg:voice:v1"


class TestHandleVoiceExceptionHandling:
    """Test handle_voice exception handling — #201."""

    def _make_voice_message(self):
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

    @pytest.mark.asyncio
    async def test_post_pipeline_error_still_writes_scores(self, mock_config):
        """When ainvoke succeeds but ChatActionSender __aexit__ throws,
        scores and trace output should still be written (#201)."""
        bot, _ = _create_bot(mock_config)

        pipeline_result = {
            "response": "ok",
            "query_type": "FAQ",
            "latency_stages": {},
            "stt_text": "test query",
        }
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=pipeline_result)
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()

            # ChatActionSender __aexit__ throws (e.g. Telegram API error)
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock(side_effect=RuntimeError("telegram API error"))
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            # Scores and trace output MUST be written despite the post-pipeline error
            mock_lf.update_current_trace.assert_called_once()
            mock_write_scores.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_pipeline_error_does_not_send_false_error(self, mock_config):
        """When pipeline succeeds but post-invoke fails, user should NOT
        receive 'Не удалось распознать' error message (#201)."""
        bot, _ = _create_bot(mock_config)

        pipeline_result = {
            "response": "answer delivered via streaming",
            "query_type": "FAQ",
            "latency_stages": {},
            "stt_text": "test query",
        }
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=pipeline_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot._write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock(side_effect=RuntimeError("cleanup error"))
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            # No error message sent — answer was already delivered
            for call in message.answer.call_args_list:
                assert "Не удалось распознать" not in str(call)

    @pytest.mark.asyncio
    async def test_genuine_pipeline_failure_sends_error(self, mock_config):
        """When ainvoke itself throws (pipeline failed), user should get error message."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot._write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock(return_value=False)
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            # Error message should be sent
            message.answer.assert_called()
            error_sent = any(
                "Не удалось распознать" in str(call) for call in message.answer.call_args_list
            )
            assert error_sent, "Error message should be sent on genuine pipeline failure"

            # Scores should NOT be written (no result)
            mock_write_scores.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_error_with_no_result_does_not_send_false_error(self, mock_config):
        """Cleanup failures from AsyncPregelLoop.__aexit__ should not send extra user error."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            side_effect=RuntimeError(
                "AsyncPregelLoop.__aexit__ failed: psycopg.OperationalError: connection lost"
            )
        )
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock(return_value=False)
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            # No extra "recognition failed" message: response may already be delivered.
            error_sent = any(
                "Не удалось распознать" in str(call) for call in message.answer.call_args_list
            )
            assert not error_sent
            # #205: even on cleanup failure, trace metadata and scores must be persisted.
            mock_lf.update_current_trace.assert_called_once()
            mock_write_scores.assert_called_once()

    @pytest.mark.asyncio
    async def test_scores_written_even_if_trace_update_fails(self, mock_config):
        """Trace update failure should not prevent score writes (#202 review)."""
        bot, _ = _create_bot(mock_config)

        pipeline_result = {
            "response": "ok",
            "query_type": "FAQ",
            "latency_stages": {},
            "stt_text": "test query",
        }
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=pipeline_result)
        mock_lf = MagicMock()
        mock_lf.update_current_trace.side_effect = RuntimeError("trace write failed")

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot._write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock(return_value=False)
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            mock_write_scores.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_transcription_returns_speech_error(self, mock_config):
        """Empty transcription ValueError should show 'не содержит речи' message."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            side_effect=ValueError("Empty transcription from Whisper API")
        )

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()

            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = AsyncMock()
                mock_cm.__aenter__ = AsyncMock()
                mock_cm.__aexit__ = AsyncMock(return_value=False)
                mock_cas.typing.return_value = mock_cm

                await bot.handle_voice(message)

            message.answer.assert_called()
            speech_error = any(
                "не содержит речи" in str(call) for call in message.answer.call_args_list
            )
            assert speech_error


class TestBotLifecycle:
    """Test bot start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_initializes_cache(self, mock_config):
        """Test that start() initializes cache."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()

        with patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock):
            await bot.start()

        bot._cache.initialize.assert_called_once()
        bot.dp.start_polling.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_skips_reinit_if_already_initialized(self, mock_config):
        """Test that start() skips cache init if already done."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot._cache_initialized = True
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()

        with patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock):
            await bot.start()

        bot._cache.initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_closes_services(self, mock_config):
        """Test that stop() closes all services."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.close = AsyncMock()
        bot._qdrant = MagicMock()
        bot._qdrant.close = AsyncMock()
        bot._embeddings = MagicMock()
        bot._embeddings.aclose = AsyncMock()
        bot._sparse = MagicMock()
        bot._sparse.aclose = AsyncMock()
        bot._reranker = None
        bot.bot = MagicMock()
        bot.bot.session = MagicMock()
        bot.bot.session.close = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.stop = AsyncMock()

        await bot.stop()

        bot._cache.close.assert_called_once()
        bot._qdrant.close.assert_called_once()
        bot._embeddings.aclose.assert_awaited_once()
        bot._sparse.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_closes_checkpointer_context(self, mock_config):
        """stop() should close async checkpointer context when available."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.close = AsyncMock()
        bot._qdrant = MagicMock()
        bot._qdrant.close = AsyncMock()
        bot._embeddings = MagicMock()
        bot._embeddings.aclose = AsyncMock()
        bot._sparse = MagicMock()
        bot._sparse.aclose = AsyncMock()
        bot._reranker = None
        bot.bot = MagicMock()
        bot.bot.session = MagicMock()
        bot.bot.session.close = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.stop = AsyncMock()
        bot._checkpointer = MagicMock()
        bot._checkpointer.__aexit__ = AsyncMock()
        checkpointer = bot._checkpointer

        await bot.stop()

        checkpointer.__aexit__.assert_awaited_once_with(None, None, None)


class TestSetupMiddlewares:
    """Test middleware setup."""

    @patch("telegram_bot.bot.setup_throttling_middleware")
    @patch("telegram_bot.bot.setup_error_middleware")
    def test_middlewares_configured(self, mock_error_mw, mock_throttle_mw, mock_config):
        """Test that middlewares are configured on init."""
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.integrations.cache.CacheLayerManager"),
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
            patch("telegram_bot.services.qdrant.QdrantService"),
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        ):
            PropertyBot(mock_config)

        mock_throttle_mw.assert_called_once()
        mock_error_mw.assert_called_once()


class TestRegisterHandlers:
    """Test handler registration."""

    def test_handlers_registered(self, mock_config):
        """Test that handlers are registered on init."""
        bot, _ = _create_bot(mock_config)

        assert hasattr(bot, "cmd_start")
        assert hasattr(bot, "cmd_help")
        assert hasattr(bot, "cmd_clear")
        assert hasattr(bot, "cmd_stats")
        assert hasattr(bot, "handle_query")


class TestWriteLangfuseScores:
    """Test _write_langfuse_scores score writing."""

    def test_latency_total_ms_uses_wall_time(self):
        """latency_total_ms should use pipeline_wall_ms from state, not sum of stages."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "GENERAL",
            "cache_hit": False,
            "search_results_count": 20,
            "rerank_applied": False,
            "latency_stages": {"cache_check": 5.0, "retrieve": 8.0, "generate": 3.0},
            "pipeline_wall_ms": 7500.0,  # wall-time set by handle_query
        }
        _write_langfuse_scores(mock_lf, result)
        # Find the latency_total_ms call
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["latency_total_ms"] == 7500.0

    def test_latency_total_ms_fallback_zero(self):
        """Without pipeline_wall_ms, latency_total_ms should be 0."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {"query_type": "FAQ", "latency_stages": {}}
        _write_langfuse_scores(mock_lf, result)
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["latency_total_ms"] == 0.0

    def test_real_scores_from_state(self):
        """Hardcoded scores should now use real state values."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "FAQ",
            "cache_hit": False,
            "search_results_count": 20,
            "rerank_applied": True,
            "latency_stages": {"generate": 1.0},
            "pipeline_wall_ms": 5000.0,
            "embeddings_cache_hit": True,
            "search_cache_hit": False,
            "grade_confidence": 0.016,
        }
        _write_langfuse_scores(mock_lf, result)
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["embeddings_cache_hit"] == 1.0
        assert calls["search_cache_hit"] == 0.0
        assert calls["confidence_score"] == 0.016

    def test_write_langfuse_scores_includes_ttft(self):
        """llm_ttft_ms and llm_response_duration_ms are written as scores."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "GENERAL",
            "cache_hit": False,
            "search_results_count": 5,
            "rerank_applied": False,
            "latency_stages": {"generate": 2.5},
            "pipeline_wall_ms": 3000.0,
            "llm_ttft_ms": 450.0,
            "llm_response_duration_ms": 2500.0,
        }
        _write_langfuse_scores(mock_lf, result)
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["llm_ttft_ms"] == 450.0
        assert calls["llm_response_duration_ms"] == 2500.0

    def test_writes_embedding_error_score(self):
        """_write_langfuse_scores writes bge_embed_error when embedding failed."""
        from telegram_bot.bot import _write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "FAQ",
            "cache_hit": True,
            "embedding_error": True,
            "embedding_error_type": "RemoteProtocolError",
            "latency_stages": {"cache_check": 5.123},
            "pipeline_wall_ms": 5200.0,
            "user_perceived_wall_ms": 5200.0,
        }
        _write_langfuse_scores(mock_lf, result)

        calls = {
            c.kwargs["name"]: c.kwargs.get("value")
            for c in mock_lf.score_current_trace.call_args_list
            if "name" in c.kwargs
        }
        assert calls["bge_embed_error"] == 1
        assert "bge_embed_latency_ms" in calls


class TestMakeSessionId:
    """Test make_session_id utility function."""

    def test_format(self):
        """Test session ID format."""
        sid = make_session_id("chat", 12345)
        assert sid.startswith("chat-")
        parts = sid.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # hash

    def test_deterministic(self):
        """Same inputs produce same session ID."""
        sid1 = make_session_id("chat", 12345)
        sid2 = make_session_id("chat", 12345)
        assert sid1 == sid2

    def test_different_ids(self):
        """Different identifiers produce different session IDs."""
        sid1 = make_session_id("chat", 12345)
        sid2 = make_session_id("chat", 67890)
        assert sid1 != sid2
