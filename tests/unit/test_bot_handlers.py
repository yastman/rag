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
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
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


def _make_text_message(text="test", user_id=12345, chat_id=12345):
    """Create a mock text message with typing action support."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=user_id)
    message.chat = MagicMock(id=chat_id)
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


def _make_typing_cm():
    """Create a mock ChatActionSender.typing() context manager.

    __aexit__ returns False by default so exceptions propagate normally.
    """
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock()
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


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
            patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
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
            patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
        ):
            PropertyBot(mock_config)

        assert mock_qdrant.call_args.kwargs["timeout"] == 7

    def test_init_creates_llm_guard_client_when_enabled(self, mock_config):
        """PropertyBot initializes LLMGuardClient when ML guard is enabled."""
        mock_config.guard_ml_enabled = True
        mock_config.llm_guard_url = "http://guard:8100"
        with (
            patch("telegram_bot.bot.Bot"),
            patch("telegram_bot.integrations.cache.CacheLayerManager"),
            patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
            patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
            patch("telegram_bot.services.qdrant.QdrantService"),
            patch("telegram_bot.graph.config.GraphConfig.create_llm"),
            patch("telegram_bot.services.llm_guard_client.LLMGuardClient") as mock_guard_client,
        ):
            bot = PropertyBot(mock_config)

        mock_guard_client.assert_called_once_with(base_url="http://guard:8100")
        assert bot._llm_guard_client is mock_guard_client.return_value


class TestCommandHandlers:
    """Test command handlers."""

    @pytest.mark.parametrize(
        ("handler_name", "expected_fragments"),
        [
            ("cmd_start", ["assistant", "недвижимость"]),
            ("cmd_help", ["Примеры запросов", "/clear", "/stats"]),
        ],
    )
    async def test_simple_commands(self, mock_config, handler_name, expected_fragments):
        """Test /start and /help produce expected response text."""
        bot, _ = _create_bot(mock_config)
        message = _make_text_message()

        await getattr(bot, handler_name)(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        for fragment in expected_fragments:
            assert fragment in call_args

    async def test_cmd_start_manager_receives_manager_menu(self, mock_config):
        """Manager user receives manager-specific start menu (#388)."""
        mock_config.manager_ids = [12345]
        bot, _ = _create_bot(mock_config)
        message = _make_text_message(user_id=12345)

        await bot.cmd_start(message)

        sent = message.answer.call_args[0][0]
        assert "Manager menu" in sent

    async def test_resolve_user_role_prefers_config_manager_ids_on_db_client(self, mock_config):
        """manager_ids fallback should elevate manager even when DB returns client (#388)."""
        mock_config.manager_ids = [12345]
        bot, _ = _create_bot(mock_config)
        bot._user_service = AsyncMock()
        bot._user_service.get_role = AsyncMock(return_value="client")

        role = await bot._resolve_user_role(12345)

        assert role == "manager"

    async def test_cmd_clear(self, mock_config):
        """Test /clear command handler."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        message = _make_text_message()

        await bot.cmd_clear(message)

        bot._cache.clear_conversation.assert_called_once_with(12345)
        message.answer.assert_called_once()
        assert "очищена" in message.answer.call_args[0][0].lower()

    async def test_cmd_clear_uses_checkpointer_delete_thread(self, mock_config):
        """Test /clear calls checkpointer.adelete_thread for SDK-native cleanup."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        bot._checkpointer = AsyncMock()
        message = _make_text_message()

        await bot.cmd_clear(message)

        bot._checkpointer.adelete_thread.assert_awaited_once_with("12345")
        bot._cache.clear_conversation.assert_awaited_once_with(12345)

    async def test_cmd_clear_handles_no_checkpointer(self, mock_config):
        """Test /clear works when checkpointer is None (fallback)."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        bot._checkpointer = None
        message = _make_text_message()

        await bot.cmd_clear(message)

        bot._cache.clear_conversation.assert_awaited_once_with(12345)
        message.answer.assert_called_once()

    async def test_cmd_clear_reports_partial_failure_on_checkpointer_error(self, mock_config):
        """Test /clear reports partial failure when checkpointer deletion fails."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.clear_conversation = AsyncMock()
        bot._checkpointer = AsyncMock()
        bot._checkpointer.adelete_thread = AsyncMock(side_effect=RuntimeError("redis down"))
        message = _make_text_message()

        await bot.cmd_clear(message)

        bot._cache.clear_conversation.assert_awaited_once_with(12345)
        bot._checkpointer.adelete_thread.assert_awaited_once_with("12345")
        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args.args[0]
        assert "частично" in answer_text.lower()

    async def test_cmd_stats(self, mock_config):
        """Test /stats command handler."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.get_metrics.return_value = {
            "semantic": {"hit_rate": 80.0, "hits": 40, "total": 50},
            "embeddings": {"hit_rate": 70.0, "hits": 35, "total": 50},
        }
        message = _make_text_message()

        await bot.cmd_stats(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Статистика" in call_args
        assert "80" in call_args

    async def test_cmd_stats_uses_hits_plus_misses_denominator(self, mock_config):
        """Test /stats command uses hits + misses as denominator (not 'total')."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.get_metrics.return_value = {
            "semantic": {"hit_rate": 75.0, "hits": 30, "misses": 10},
        }
        message = _make_text_message()

        await bot.cmd_stats(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        # Should show "30/40" (hits/total), where total = hits + misses
        assert "30/40" in call_args, "Expected denominator to be hits + misses = 40"

    async def test_cmd_metrics(self, mock_config):
        """Test /metrics command handler."""
        bot, _ = _create_bot(mock_config)
        message = _make_text_message()

        with patch("telegram_bot.bot.PipelineMetrics") as mock_pm:
            mock_metrics = MagicMock()
            mock_metrics.format_text.return_value = "p50=100ms p95=200ms"
            mock_pm.get.return_value = mock_metrics

            await bot.cmd_metrics(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "p50" in call_args


def _mock_supervisor_result(**overrides):
    """Create a standard supervisor graph result dict."""
    base = {
        "messages": [MagicMock(content="Supervisor response")],
        "agent_used": "rag_search",
        "latency_stages": {"supervisor": 0.1},
    }
    base.update(overrides)
    return base


class TestHandleQuery:
    """Test handle_query method — supervisor-only path (#310)."""

    async def test_handle_query_invokes_supervisor_graph(self, mock_config):
        """handle_query invokes supervisor graph (default path)."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры в Несебр")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

            mock_graph.ainvoke.assert_called_once()

    async def test_handle_query_sends_typing(self, mock_config):
        """Typing action is sent early."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

            message.bot.send_chat_action.assert_called_once_with(chat_id=12345, action="typing")

    async def test_handle_query_writes_langfuse_trace(self, mock_config):
        """handle_query updates Langfuse trace with supervisor metadata."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

            mock_lf.update_current_trace.assert_called_once()
            trace_kwargs = mock_lf.update_current_trace.call_args.kwargs
            assert trace_kwargs["metadata"]["pipeline_mode"] == "supervisor"

    async def test_handle_query_writes_supervisor_scores(self, mock_config):
        """handle_query writes agent_used, supervisor_latency_ms, supervisor_model scores."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())
        mock_lf = MagicMock()

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

            score_calls = {
                c.kwargs["name"]: c.kwargs.get("value")
                for c in mock_lf.score_current_trace.call_args_list
            }
            assert "agent_used" in score_calls
            assert "supervisor_latency_ms" in score_calls
            assert "supervisor_model" in score_calls

    async def test_handle_query_passes_guard_config_to_rag_agent(self, mock_config):
        """Supervisor path forwards guard settings into create_rag_agent."""
        mock_config.content_filter_enabled = False
        mock_config.guard_mode = "soft"
        mock_config.guard_ml_enabled = True
        mock_config.max_llm_calls = 11
        bot, _ = _create_bot(mock_config)
        bot._llm_guard_client = MagicMock()
        bot._graph_config.max_rewrite_attempts = 4
        bot._graph_config.show_sources = False

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.agents.rag_agent.create_rag_agent",
                return_value=MagicMock(),
            ) as mock_create_rag_agent,
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        kwargs = mock_create_rag_agent.call_args.kwargs
        assert kwargs["content_filter_enabled"] is False
        assert kwargs["guard_mode"] == "soft"
        assert kwargs["guard_ml_enabled"] is True
        assert kwargs["llm_guard_client"] is bot._llm_guard_client
        assert kwargs["max_rewrite_attempts"] == 4
        assert kwargs["show_sources"] is False
        assert kwargs["max_llm_calls"] == 11

    async def test_handle_query_passes_max_tool_calls_to_supervisor_state(self, mock_config):
        """Supervisor invocation state uses configured max_tool_calls."""
        mock_config.max_tool_calls = 9
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        state_arg = mock_graph.ainvoke.call_args.args[0]
        assert state_arg["max_tool_calls"] == 9

    async def test_handle_query_passes_role_in_configurable(self, mock_config):
        """Supervisor config should include resolved role for role-aware tools (#390)."""
        bot, _ = _create_bot(mock_config)
        bot._resolve_user_role = AsyncMock(return_value="manager")

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        cfg = mock_graph.ainvoke.call_args.kwargs["config"]["configurable"]
        assert cfg["role"] == "manager"

    async def test_handle_query_skips_crm_tools_for_client_role(self, mock_config):
        """CRM tools are not injected for non-manager users (#389)."""
        mock_config.kommo_enabled = True
        bot, _ = _create_bot(mock_config)
        bot._kommo_client = AsyncMock()
        bot._resolve_user_role = AsyncMock(return_value="client")

        crm_tool = MagicMock()
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.agents.crm_tools.create_crm_tools", return_value=[crm_tool]
            ) as crm_factory,
            patch(
                "telegram_bot.bot.build_supervisor_graph", return_value=mock_graph
            ) as build_graph,
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        crm_factory.assert_not_called()
        tools_passed = build_graph.call_args.kwargs["tools"]
        assert crm_tool not in tools_passed

    async def test_handle_query_adds_crm_tools_for_manager_role(self, mock_config):
        """CRM tools are injected for manager users when Kommo is enabled (#389)."""
        mock_config.kommo_enabled = True
        bot, _ = _create_bot(mock_config)
        bot._kommo_client = AsyncMock()
        bot._resolve_user_role = AsyncMock(return_value="manager")

        crm_tool = MagicMock()
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.agents.crm_tools.create_crm_tools", return_value=[crm_tool]
            ) as crm_factory,
            patch(
                "telegram_bot.bot.build_supervisor_graph", return_value=mock_graph
            ) as build_graph,
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        crm_factory.assert_called_once()
        tools_passed = build_graph.call_args.kwargs["tools"]
        assert crm_tool in tools_passed

    async def test_handle_query_skips_score_sync_tool_for_client_role(self, mock_config):
        """Lead score sync tool is manager-only (#384)."""
        mock_config.kommo_enabled = True
        mock_config.kommo_lead_score_field_id = 701
        mock_config.kommo_lead_band_field_id = 702
        bot, _ = _create_bot(mock_config)
        bot._kommo_client = AsyncMock()
        bot._lead_scoring_store = AsyncMock()
        bot._resolve_user_role = AsyncMock(return_value="client")

        score_tool = MagicMock()
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.agents.tools.create_crm_score_sync_tool", return_value=score_tool
            ) as score_factory,
            patch(
                "telegram_bot.bot.build_supervisor_graph", return_value=mock_graph
            ) as build_graph,
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        score_factory.assert_not_called()
        tools_passed = build_graph.call_args.kwargs["tools"]
        assert score_tool not in tools_passed

    async def test_handle_query_adds_score_sync_tool_for_manager_with_fields(self, mock_config):
        """Lead score sync tool is added for manager when Kommo field ids are configured."""
        mock_config.kommo_enabled = True
        mock_config.kommo_lead_score_field_id = 701
        mock_config.kommo_lead_band_field_id = 702
        bot, _ = _create_bot(mock_config)
        bot._kommo_client = AsyncMock()
        bot._lead_scoring_store = AsyncMock()
        bot._resolve_user_role = AsyncMock(return_value="manager")

        score_tool = MagicMock()
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.agents.tools.create_crm_score_sync_tool", return_value=score_tool
            ) as score_factory,
            patch(
                "telegram_bot.bot.build_supervisor_graph", return_value=mock_graph
            ) as build_graph,
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        score_factory.assert_called_once()
        tools_passed = build_graph.call_args.kwargs["tools"]
        assert score_tool in tools_passed

    async def test_handle_query_skips_score_sync_tool_when_field_ids_missing(self, mock_config):
        """Lead score sync tool is not added when Kommo field ids are unset."""
        mock_config.kommo_enabled = True
        mock_config.kommo_lead_score_field_id = 0
        mock_config.kommo_lead_band_field_id = 0
        bot, _ = _create_bot(mock_config)
        bot._kommo_client = AsyncMock()
        bot._lead_scoring_store = AsyncMock()
        bot._resolve_user_role = AsyncMock(return_value="manager")

        score_tool = MagicMock()
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.agents.tools.create_crm_score_sync_tool", return_value=score_tool
            ) as score_factory,
            patch(
                "telegram_bot.bot.build_supervisor_graph", return_value=mock_graph
            ) as build_graph,
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        score_factory.assert_not_called()
        tools_passed = build_graph.call_args.kwargs["tools"]
        assert score_tool not in tools_passed


class TestHistorySaveOnResponse:
    """Test Q&A history persistence after successful responses."""

    async def test_handle_query_saves_history(self, mock_config):
        """handle_query (supervisor) stores history record when response exists."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.save_turn = AsyncMock(return_value=True)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value=_mock_supervisor_result(
                messages=[MagicMock(content="Вот квартиры...")],
            )
        )

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("квартиры в Несебр")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

        bot._history_service.save_turn.assert_awaited_once()
        call_kwargs = bot._history_service.save_turn.call_args.kwargs
        assert call_kwargs["user_id"] == 12345
        assert call_kwargs["query"] == "квартиры в Несебр"
        assert call_kwargs["response"] == "Вот квартиры..."
        assert call_kwargs["input_type"] == "text"

    async def test_handle_voice_saves_history(self, mock_config):
        """handle_voice stores history with resolved textual query."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.save_turn = AsyncMock(return_value=True)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "response": "Ответ на голос",
                "query_type": "FAQ",
                "latency_stages": {},
                "stt_text": "распознанный текст",
                "query_embedding": [0.2] * 1024,
                "input_type": "voice",
            }
        )

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.write_langfuse_scores"),
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
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

        bot._history_service.save_turn.assert_awaited_once()
        call_kwargs = bot._history_service.save_turn.call_args.kwargs
        assert call_kwargs["input_type"] == "voice"
        assert call_kwargs["query"] == "распознанный текст"

    async def test_handle_query_skips_history_when_no_service(self, mock_config):
        """handle_query (supervisor) skips history save when service is None."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = None

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                # Should not raise
                await bot.handle_query(message)

    async def test_handle_query_history_save_failure_does_not_break_response(self, mock_config):
        """History save failure should not break user response flow (supervisor)."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.save_turn = AsyncMock(side_effect=RuntimeError("save failed"))

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch("telegram_bot.bot.build_supervisor_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                # Should not raise despite save failure
                await bot.handle_query(message)


class TestCmdHistory:
    """Test /history command handler."""

    async def test_history_no_args_shows_usage(self, mock_config):
        """/history without argument shows usage message."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        message = _make_text_message("/history")

        await bot.cmd_history(message)

        message.answer.assert_called_once()
        assert (
            "использование" in message.answer.call_args[0][0].lower()
            or "/history" in message.answer.call_args[0][0]
        )

    async def test_history_search_returns_results(self, mock_config):
        """/history цены performs search and returns formatted results."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(
            return_value=[
                {
                    "query": "цены на квартиры",
                    "response": "Квартиры от 50к евро",
                    "timestamp": "2026-02-13T10:00:00",
                    "score": 0.95,
                },
            ]
        )
        message = _make_text_message("/history цены")

        await bot.cmd_history(message)

        bot._history_service.search_user_history.assert_awaited_once_with(
            user_id=12345, query="цены", limit=5
        )
        message.answer.assert_called_once()
        answer_text = message.answer.call_args[0][0]
        assert "цены на квартиры" in answer_text
        assert "Квартиры от 50к евро" in answer_text

    async def test_history_empty_results(self, mock_config):
        """/history with no matches returns informative message."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(return_value=[])
        message = _make_text_message("/history несуществующее")

        await bot.cmd_history(message)

        message.answer.assert_called_once()
        assert (
            "не найден" in message.answer.call_args[0][0].lower()
            or "нет" in message.answer.call_args[0][0].lower()
        )

    async def test_history_unavailable_fallback(self, mock_config):
        """/history when service is None returns graceful message."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = None
        message = _make_text_message("/history цены")

        await bot.cmd_history(message)

        message.answer.assert_called_once()
        assert "недоступн" in message.answer.call_args[0][0].lower()

    def test_history_command_registered(self, mock_config):
        """Verify /history handler is registered."""
        bot, _ = _create_bot(mock_config)
        assert hasattr(bot, "cmd_history")

    async def test_history_backend_exception_returns_safe_message(self, mock_config):
        """Backend exception is caught and user gets a safe error message."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(
            side_effect=RuntimeError("connection lost")
        )
        message = _make_text_message("/history цены")

        with patch("telegram_bot.bot.get_client", return_value=MagicMock()):
            with patch("telegram_bot.bot.propagate_attributes"):
                await bot.cmd_history(message)

        message.answer.assert_called_once()
        answer_text = message.answer.call_args[0][0]
        assert "ошибка" in answer_text.lower()

    async def test_history_malformed_payload_skips_bad_records(self, mock_config):
        """Malformed results (None, str, dict without keys) are skipped; valid ones shown."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(
            return_value=[
                None,
                "not a dict",
                {"query": 123, "response": "text"},
                {"other_key": "value"},
                {
                    "query": "валидный вопрос",
                    "response": "валидный ответ",
                    "timestamp": "2026-02-13T10:00:00",
                },
            ]
        )
        message = _make_text_message("/history тест")

        with patch("telegram_bot.bot.get_client", return_value=MagicMock()):
            with patch("telegram_bot.bot.propagate_attributes"):
                await bot.cmd_history(message)

        message.answer.assert_called_once()
        answer_text = message.answer.call_args[0][0]
        assert "валидный вопрос" in answer_text
        assert "валидный ответ" in answer_text
        assert "1 записей" in answer_text
        assert "1. [" in answer_text

    async def test_history_all_malformed_returns_not_found(self, mock_config):
        """When all results are malformed, user sees 'not found' fallback."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(
            return_value=[None, "bad", {"no_query": True}]
        )
        message = _make_text_message("/history тест")

        with patch("telegram_bot.bot.get_client", return_value=MagicMock()):
            with patch("telegram_bot.bot.propagate_attributes"):
                await bot.cmd_history(message)

        message.answer.assert_called_once()
        answer_text = message.answer.call_args[0][0]
        assert "не найден" in answer_text.lower() or "нет" in answer_text.lower()

    async def test_history_search_writes_langfuse_scores(self, mock_config):
        """Successful /history search writes trace + 4 scores."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(
            return_value=[
                {
                    "query": "цены",
                    "response": "Ответ",
                    "timestamp": "2026-02-13T10:00:00",
                    "score": 0.9,
                },
            ]
        )
        message = _make_text_message("/history цены")

        mock_lf = MagicMock()
        with patch("telegram_bot.bot.get_client", return_value=mock_lf):
            with patch("telegram_bot.bot.propagate_attributes"):
                await bot.cmd_history(message)

        # Trace metadata
        mock_lf.update_current_trace.assert_called_once()
        trace_kwargs = mock_lf.update_current_trace.call_args[1]
        assert trace_kwargs["input"]["command"] == "/history"
        assert trace_kwargs["input"]["query"] == "цены"
        assert trace_kwargs["output"]["results_count"] == 1

        # Scores
        score_calls = mock_lf.score_current_trace.call_args_list
        score_names = [c[1]["name"] for c in score_calls]
        assert "history_search_count" in score_names
        assert "history_search_latency_ms" in score_names
        assert "history_search_empty" in score_names
        assert "history_backend" in score_names

        # Verify values
        score_map = {c[1]["name"]: c[1]["value"] for c in score_calls}
        assert score_map["history_search_count"] == 1
        assert score_map["history_search_empty"] == 0.0
        assert score_map["history_backend"] == "qdrant"
        assert isinstance(score_map["history_search_latency_ms"], float)

    async def test_history_empty_writes_langfuse_scores(self, mock_config):
        """Empty /history result writes history_search_empty=1.0."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = AsyncMock()
        bot._history_service.search_user_history = AsyncMock(return_value=[])
        message = _make_text_message("/history несуществующее")

        mock_lf = MagicMock()
        with patch("telegram_bot.bot.get_client", return_value=mock_lf):
            with patch("telegram_bot.bot.propagate_attributes"):
                await bot.cmd_history(message)

        score_calls = mock_lf.score_current_trace.call_args_list
        score_map = {c[1]["name"]: c[1]["value"] for c in score_calls}
        assert score_map["history_search_count"] == 0
        assert score_map["history_search_empty"] == 1.0

    async def test_history_unavailable_writes_langfuse_scores(self, mock_config):
        """Unavailable service writes scores with error metadata."""
        bot, _ = _create_bot(mock_config)
        bot._history_service = None
        message = _make_text_message("/history цены")

        mock_lf = MagicMock()
        with patch("telegram_bot.bot.get_client", return_value=mock_lf):
            with patch("telegram_bot.bot.propagate_attributes"):
                await bot.cmd_history(message)

        # Trace should indicate error
        trace_kwargs = mock_lf.update_current_trace.call_args[1]
        assert trace_kwargs["output"]["error"] == "service_unavailable"

        # Scores
        score_calls = mock_lf.score_current_trace.call_args_list
        score_map = {c[1]["name"]: c[1]["value"] for c in score_calls}
        assert score_map["history_search_count"] == 0
        assert score_map["history_search_empty"] == 1.0


class TestCheckpointNamespace:
    """Test checkpoint namespace separation for voice (text uses supervisor path)."""

    async def test_handle_voice_passes_voice_checkpoint_ns(self, mock_config):
        """handle_voice passes checkpoint_ns='tg:voice:v1' in invoke_config."""
        bot, _ = _create_bot(mock_config)
        bot._llm_guard_client = MagicMock()

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
            patch("telegram_bot.bot.build_graph", return_value=mock_graph) as mock_build_graph,
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.write_langfuse_scores"),
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
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

            cfg = mock_graph.ainvoke.call_args.kwargs["config"]["configurable"]
            assert cfg["thread_id"] == "12345"
            assert cfg["checkpoint_ns"] == "tg:voice:v1"
            graph_kwargs = mock_build_graph.call_args.kwargs
            assert graph_kwargs["llm_guard_client"] is bot._llm_guard_client


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
            patch("telegram_bot.bot.write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = _make_typing_cm()
                mock_cm.__aexit__ = AsyncMock(side_effect=RuntimeError("telegram API error"))
                mock_cas.typing.return_value = mock_cm
                await bot.handle_voice(message)

            mock_lf.update_current_trace.assert_called_once()
            mock_write_scores.assert_called_once()

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
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cm = _make_typing_cm()
                mock_cm.__aexit__ = AsyncMock(side_effect=RuntimeError("cleanup error"))
                mock_cas.typing.return_value = mock_cm
                await bot.handle_voice(message)

            for call in message.answer.call_args_list:
                assert "Не удалось распознать" not in str(call)

    async def test_genuine_pipeline_failure_sends_error(self, mock_config):
        """When ainvoke itself throws (pipeline failed), user should get error message."""
        bot, _ = _create_bot(mock_config)

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

            message.answer.assert_called()
            error_sent = any(
                "Не удалось распознать" in str(call) for call in message.answer.call_args_list
            )
            assert error_sent, "Error message should be sent on genuine pipeline failure"
            mock_write_scores.assert_not_called()

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
            patch("telegram_bot.bot.write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

            error_sent = any(
                "Не удалось распознать" in str(call) for call in message.answer.call_args_list
            )
            assert not error_sent
            mock_lf.update_current_trace.assert_called_once()
            mock_write_scores.assert_called_once()

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
            patch("telegram_bot.bot.write_langfuse_scores") as mock_write_scores,
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = self._make_voice_message()
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

            mock_write_scores.assert_called_once()

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
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_voice(message)

            message.answer.assert_called()
            speech_error = any(
                "не содержит речи" in str(call) for call in message.answer.call_args_list
            )
            assert speech_error


class TestBotLifecycle:
    """Test bot start/stop lifecycle."""

    async def test_start_initializes_cache(self, mock_config):
        """Test that start() initializes cache."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()
        bot.bot = MagicMock()
        bot.bot.set_my_commands = AsyncMock()

        with patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock):
            await bot.start()

        bot._cache.initialize.assert_called_once()
        bot.dp.start_polling.assert_called_once()

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
        bot.bot = MagicMock()
        bot.bot.set_my_commands = AsyncMock()

        with patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock):
            await bot.start()

        bot._cache.initialize.assert_not_called()

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
        bot._llm_guard_client = MagicMock()
        bot._llm_guard_client.aclose = AsyncMock()
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
        bot._llm_guard_client.aclose.assert_awaited_once()

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


class TestHistoryServiceLifecycle:
    """Test history service initialization in bot lifecycle."""

    async def test_start_initializes_history_service(self, mock_config):
        """start() should create and ensure history collection."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()
        bot.bot = MagicMock()
        bot.bot.set_my_commands = AsyncMock()

        mock_checkpointer = AsyncMock()
        with (
            patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock),
            patch(
                "telegram_bot.integrations.memory.create_redis_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch("telegram_bot.bot.HistoryService") as mock_history_cls,
        ):
            mock_svc = AsyncMock()
            mock_history_cls.return_value = mock_svc
            await bot.start()

        assert bot._history_service is not None
        mock_svc.ensure_collection.assert_awaited_once()

    async def test_start_history_failure_does_not_crash(self, mock_config):
        """start() should not crash if history service init fails."""
        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()
        bot.bot = MagicMock()
        bot.bot.set_my_commands = AsyncMock()

        mock_checkpointer = AsyncMock()
        with (
            patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock),
            patch(
                "telegram_bot.integrations.memory.create_redis_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch("telegram_bot.bot.HistoryService") as mock_history_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc.ensure_collection = AsyncMock(side_effect=RuntimeError("qdrant down"))
            mock_history_cls.return_value = mock_svc
            # Should not raise
            await bot.start()

        assert bot._history_service is None

    async def test_stop_safe_without_history_service(self, mock_config):
        """stop() should work fine when history_service is None."""
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
        bot._history_service = None

        # Should not raise
        await bot.stop()


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
            patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
        ):
            PropertyBot(mock_config)

        mock_throttle_mw.assert_called_once()
        mock_error_mw.assert_called_once()


class TestRegisterHandlers:
    """Test handler registration."""

    @pytest.mark.parametrize(
        "handler_name",
        ["cmd_start", "cmd_help", "cmd_clear", "cmd_stats", "handle_query"],
    )
    def test_handler_registered(self, mock_config, handler_name):
        """Test that expected handler is registered on init."""
        bot, _ = _create_bot(mock_config)
        assert hasattr(bot, handler_name)


class TestWriteLangfuseScores:
    """Test write_langfuse_scores score writing (canonical in scoring.py)."""

    def test_latency_total_ms_uses_wall_time(self):
        """latency_total_ms should use pipeline_wall_ms from state, not sum of stages."""
        from telegram_bot.scoring import write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "GENERAL",
            "cache_hit": False,
            "search_results_count": 20,
            "rerank_applied": False,
            "latency_stages": {"cache_check": 5.0, "retrieve": 8.0, "generate": 3.0},
            "pipeline_wall_ms": 7500.0,  # wall-time set by handle_query
        }
        write_langfuse_scores(mock_lf, result)
        # Find the latency_total_ms call
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["latency_total_ms"] == 7500.0

    def test_latency_total_ms_fallback_zero(self):
        """Without pipeline_wall_ms, latency_total_ms should be 0."""
        from telegram_bot.scoring import write_langfuse_scores

        mock_lf = MagicMock()
        result = {"query_type": "FAQ", "latency_stages": {}}
        write_langfuse_scores(mock_lf, result)
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["latency_total_ms"] == 0.0

    def test_real_scores_from_state(self):
        """Hardcoded scores should now use real state values."""
        from telegram_bot.scoring import write_langfuse_scores

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
        write_langfuse_scores(mock_lf, result)
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["embeddings_cache_hit"] == 1.0
        assert calls["search_cache_hit"] == 0.0
        assert calls["confidence_score"] == 0.016

    def test_write_langfuse_scores_includes_ttft(self):
        """llm_ttft_ms and llm_response_duration_ms are written as scores."""
        from telegram_bot.scoring import write_langfuse_scores

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
        write_langfuse_scores(mock_lf, result)
        calls = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert calls["llm_ttft_ms"] == 450.0
        assert calls["llm_response_duration_ms"] == 2500.0

    def test_writes_embedding_error_score(self):
        """write_langfuse_scores writes bge_embed_error when embedding failed."""
        from telegram_bot.scoring import write_langfuse_scores

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
        write_langfuse_scores(mock_lf, result)

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
        """Test session ID format: prefix-hash8-id."""
        sid = make_session_id("chat", 12345)
        assert sid.startswith("chat-")
        parts = sid.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # hash

    @pytest.mark.parametrize(
        ("prefix", "identifier"),
        [("chat", 12345), ("voice", 99999), ("api", 1)],
    )
    def test_deterministic(self, prefix, identifier):
        """Same inputs produce same session ID."""
        assert make_session_id(prefix, identifier) == make_session_id(prefix, identifier)

    @pytest.mark.parametrize(
        ("id_a", "id_b"),
        [(12345, 67890), (1, 2)],
    )
    def test_different_ids(self, id_a, id_b):
        """Different identifiers produce different session IDs."""
        assert make_session_id("chat", id_a) != make_session_id("chat", id_b)


class TestSupervisorIntegration:
    """Test supervisor-only query path (#310)."""

    async def test_handle_query_always_uses_supervisor(self, mock_config):
        """handle_query always uses supervisor graph (default since #310)."""
        bot, _ = _create_bot(mock_config)

        mock_supervisor_graph = AsyncMock()
        mock_supervisor_graph.ainvoke = AsyncMock(return_value=_mock_supervisor_result())

        with (
            patch(
                "telegram_bot.bot.build_supervisor_graph",
                return_value=mock_supervisor_graph,
            ),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
        ):
            message = _make_text_message("цены на квартиры")
            with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
                mock_cas.typing.return_value = _make_typing_cm()
                await bot.handle_query(message)

            mock_supervisor_graph.ainvoke.assert_called_once()
