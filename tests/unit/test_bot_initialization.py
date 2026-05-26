"""Test PropertyBot initialization, start(), and helper methods."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.config import BotConfig
from telegram_bot.startup_status import StartupReport, StartupSeverity, StartupSignal


def _make_config(**overrides) -> BotConfig:
    defaults = {
        "telegram_token": "test-token",
        "llm_api_key": "llm-key",
        "llm_base_url": "https://api.example.com/v1",
        "llm_model": "gpt-4o-mini",
        "qdrant_url": "http://localhost:6333",
        "redis_url": "redis://localhost:6379",
        "rerank_provider": "none",
        "manager_ids": [123],
    }
    defaults.update(overrides)
    return BotConfig(_env_file=None, **defaults)


def _create_bot(config: BotConfig | None = None):
    if config is None:
        config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        from telegram_bot.bot import PropertyBot

        return PropertyBot(config)


class TestPropertyBotInit:
    """Verify __init__ creates all expected attributes."""

    def test_bot_and_dp_exist(self):
        bot = _create_bot()
        assert bot.bot is not None
        assert bot.dp is not None

    def test_cache_and_embeddings_exist(self):
        bot = _create_bot()
        assert bot._cache is not None
        assert bot._hybrid is not None
        assert bot._embeddings is not None
        assert bot._sparse is not None

    def test_qdrant_and_apartments_service_exist(self):
        bot = _create_bot()
        assert bot._qdrant is not None
        assert bot._apartments_service is not None

    def test_llm_exists(self):
        bot = _create_bot()
        assert bot._llm is not None

    def test_apartment_pipeline_exists(self):
        bot = _create_bot()
        assert bot._apartment_pipeline is not None

    def test_redis_monitor_exists(self):
        bot = _create_bot()
        assert bot._redis_monitor is not None

    def test_checkpointer_is_none_before_start(self):
        bot = _create_bot()
        assert bot._checkpointer is None

    def test_agent_checkpointer_is_none_before_start(self):
        bot = _create_bot()
        assert bot._agent_checkpointer is None

    def test_history_service_is_none_before_start(self):
        bot = _create_bot()
        assert bot._history_service is None

    def test_user_service_is_none_before_start(self):
        bot = _create_bot()
        assert bot._user_service is None

    def test_kommo_client_is_none_before_start(self):
        bot = _create_bot()
        assert bot._kommo_client is None

    def test_favorites_service_is_none_before_start(self):
        bot = _create_bot()
        assert bot._favorites_service is None

    def test_handoff_state_is_none_before_start(self):
        bot = _create_bot()
        assert bot._handoff_state is None

    def test_forum_bridge_is_none_before_start(self):
        bot = _create_bot()
        assert bot._forum_bridge is None

    def test_cache_initialized_is_false(self):
        bot = _create_bot()
        assert bot._cache_initialized is False

    def test_history_save_tasks_is_empty_set(self):
        bot = _create_bot()
        assert bot._history_save_tasks == set()
        assert isinstance(bot._history_save_tasks, set)


def _start_patches(bot):
    """Context manager stack that mocks all externals needed by start()."""
    mock_checkpointer = AsyncMock()
    mock_checkpointer.asetup = AsyncMock()

    mock_me = MagicMock()
    mock_me.id = 12345
    mock_me.has_topics_enabled = False

    mock_history_cls = MagicMock()
    mock_history_instance = MagicMock()
    mock_history_instance.ensure_collection = AsyncMock()
    mock_history_cls.return_value = mock_history_instance

    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch(
            "telegram_bot.preflight.check_dependencies",
            new_callable=AsyncMock,
            return_value={"postgres": True, "redis": True, "qdrant": True},
        )
    )
    stack.enter_context(
        patch(
            "telegram_bot.integrations.memory.create_redis_checkpointer",
            return_value=mock_checkpointer,
        )
    )
    stack.enter_context(
        patch(
            "telegram_bot.integrations.memory.create_fallback_checkpointer",
            return_value=MagicMock(),
        )
    )
    stack.enter_context(patch("redis.asyncio.from_url", return_value=MagicMock()))
    stack.enter_context(patch("asyncpg.connect", new_callable=AsyncMock))
    stack.enter_context(patch("asyncpg.create_pool", new_callable=AsyncMock))
    stack.enter_context(patch.object(bot._cache, "initialize", new_callable=AsyncMock))
    stack.enter_context(patch.object(bot._redis_monitor, "start", new_callable=AsyncMock))
    stack.enter_context(patch.object(bot.bot, "me", new_callable=AsyncMock, return_value=mock_me))
    stack.enter_context(
        patch.object(bot.bot, "get_me", new_callable=AsyncMock, return_value=mock_me)
    )
    stack.enter_context(patch.object(bot.bot, "set_my_commands", new_callable=AsyncMock))
    stack.enter_context(patch.object(bot.bot, "set_chat_menu_button", new_callable=AsyncMock))
    stack.enter_context(patch("telegram_bot.bot.HistoryService", mock_history_cls))
    # Prevent dialog router attachment errors (singletons already attached)
    stack.enter_context(patch.object(bot.dp, "include_router", MagicMock()))
    stack.enter_context(patch("telegram_bot.middlewares.i18n.setup_i18n_middleware", MagicMock()))
    stack.enter_context(patch("aiogram_dialog.setup_dialogs", MagicMock()))
    stack.enter_context(patch.object(bot, "_warmup_bge", new_callable=AsyncMock))
    # Prevent start_polling from actually blocking
    stack.enter_context(patch.object(bot.dp, "start_polling", new_callable=AsyncMock))
    # Mock cache.redis as None to skip polling lock and handoff sections that need real Redis
    stack.enter_context(patch.object(bot._cache, "redis", None))
    return stack


class TestPropertyBotStart:
    """Test the start() method with external services mocked."""

    async def test_successful_start_cache_initialized(self):
        bot = _create_bot()
        with _start_patches(bot):
            await bot.start()
        assert bot._cache_initialized is True

    async def test_successful_start_checkpointer_set(self):
        bot = _create_bot()
        with _start_patches(bot):
            await bot.start()
        assert bot._checkpointer is not None

    async def test_successful_start_agent_checkpointer_set(self):
        bot = _create_bot()
        with _start_patches(bot):
            await bot.start()
        assert bot._agent_checkpointer is not None

    async def test_successful_start_topic_service_set(self):
        bot = _create_bot()
        with _start_patches(bot):
            await bot.start()
        assert bot._topic_service is not None

    async def test_redis_checkpointer_failure_falls_back(self):
        """When create_redis_checkpointer raises, start() falls back to in-memory."""
        bot = _create_bot()
        mock_fallback = MagicMock()

        with _start_patches(bot):
            with (
                patch(
                    "telegram_bot.integrations.memory.create_redis_checkpointer",
                    side_effect=Exception("Redis connection refused"),
                ),
                patch(
                    "telegram_bot.integrations.memory.create_fallback_checkpointer",
                    return_value=mock_fallback,
                ),
            ):
                await bot.start()

        assert bot._checkpointer is mock_fallback

    async def test_history_service_failure_remains_none(self):
        """When HistoryService raises, _history_service stays None."""
        bot = _create_bot()
        mock_history_cls = MagicMock(side_effect=Exception("Qdrant unavailable"))

        with _start_patches(bot):
            with patch("telegram_bot.bot.HistoryService", mock_history_cls):
                await bot.start()

        assert bot._history_service is None

    async def test_preflight_failure_propagates(self):
        """When check_dependencies raises PreflightError, start() re-raises."""
        from telegram_bot.preflight import PreflightError

        bot = _create_bot()

        with (
            patch(
                "telegram_bot.preflight.check_dependencies",
                new_callable=AsyncMock,
                side_effect=PreflightError(failed_deps=["redis"], report=StartupReport()),
            ),
            pytest.raises(SystemExit),
        ):
            await bot.start()

    async def test_postgres_unavailable_adds_degraded_signal(self):
        """When preflight marks postgres=False, startup_report gets postgres_runtime DEGRADED signal."""
        bot = _create_bot()

        signals: list[StartupSignal] = []

        class _RecordingReport(StartupReport):
            def add(self, signal: StartupSignal) -> None:
                signals.append(signal)
                super().add(signal)

        with _start_patches(bot):
            with (
                patch(
                    "telegram_bot.preflight.check_dependencies",
                    new_callable=AsyncMock,
                    return_value={"postgres": False, "redis": True, "qdrant": True},
                ),
                patch("telegram_bot.bot.StartupReport", _RecordingReport),
            ):
                await bot.start()

        pg_signals = [s for s in signals if s.source == "postgres_runtime"]
        assert len(pg_signals) == 1, (
            f"Expected 1 postgres_runtime signal, got {len(pg_signals)}: {[s.summary for s in pg_signals]}"
        )
        assert pg_signals[0].severity == StartupSeverity.DEGRADED


class TestResolveUserRole:
    """Test _resolve_user_role method."""

    def _bot_with_user_service(self, user_service=None):
        config = _make_config(manager_ids=[100])
        bot = _create_bot(config)
        bot._user_service = user_service
        return bot

    async def test_user_in_manager_ids_returns_manager(self):
        bot = self._bot_with_user_service(user_service=None)
        role = await bot._resolve_user_role(100)
        assert role == "manager"

    async def test_user_service_returns_manager(self):
        svc = MagicMock()
        svc.get_role = AsyncMock(return_value="manager")
        bot = self._bot_with_user_service(user_service=svc)
        role = await bot._resolve_user_role(999)
        assert role == "manager"

    async def test_user_service_returns_client(self):
        svc = MagicMock()
        svc.get_role = AsyncMock(return_value="client")
        bot = self._bot_with_user_service(user_service=svc)
        role = await bot._resolve_user_role(999)
        assert role == "client"

    async def test_user_service_raises_falls_back_to_client(self):
        svc = MagicMock()
        svc.get_role = AsyncMock(side_effect=Exception("DB down"))
        bot = self._bot_with_user_service(user_service=svc)
        role = await bot._resolve_user_role(999)
        assert role == "client"

    async def test_user_service_none_falls_back_to_client(self):
        bot = self._bot_with_user_service(user_service=None)
        role = await bot._resolve_user_role(999)
        assert role == "client"


class TestSpawnHistorySave:
    """Test _spawn_history_save bounded fan-out."""

    async def test_under_limit_returns_task(self):
        bot = _create_bot()
        bot._history_save_max_concurrency = 32

        async def _noop():
            pass

        task = bot._spawn_history_save(_noop(), user_id=1)
        assert isinstance(task, asyncio.Task)
        # Clean up
        await task

    async def test_at_max_concurrency_returns_none(self):
        bot = _create_bot()
        bot._history_save_max_concurrency = 2

        # Fill up the set with dummy tasks
        async def _block():
            await asyncio.sleep(10)

        t1 = asyncio.create_task(_block())
        t2 = asyncio.create_task(_block())
        bot._history_save_tasks = {t1, t2}

        async def _noop():
            pass

        result = bot._spawn_history_save(_noop(), user_id=99)
        assert result is None

        # Clean up
        t1.cancel()
        t2.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1
        with pytest.raises(asyncio.CancelledError):
            await t2


class TestExtractPreAgentFilters:
    """Test _extract_pre_agent_filters."""

    async def test_returns_dict_from_extractor(self):
        bot = _create_bot()
        expected = {"rooms": 2, "district": "center"}
        mock_extractor = MagicMock()
        mock_extractor.extract_filters = MagicMock(return_value=expected)
        bot._pre_agent_filter_extractor = mock_extractor

        result = await bot._extract_pre_agent_filters("2-комнатная в центре")
        assert result == expected

    async def test_returns_empty_dict_on_exception(self):
        bot = _create_bot()
        mock_extractor = MagicMock()
        mock_extractor.extract_filters = MagicMock(side_effect=Exception("parse error"))
        bot._pre_agent_filter_extractor = mock_extractor

        result = await bot._extract_pre_agent_filters("some query")
        assert result == {}
