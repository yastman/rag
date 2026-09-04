"""Tests for _handle_query_supervisor phases (content filter, semantic cache)
and handle_query handoff mode routing.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.config import BotConfig
from tests.unit._bot_config_factory import make_bot_config as _make_config


@asynccontextmanager
async def _noop_typing(*_args, **_kwargs):
    yield


def _create_bot(config: BotConfig | None = None):
    if config is None:
        config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("src.runtime.integrations.cache.CacheLayerManager"),
        patch("src.runtime.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("src.runtime.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("src.runtime.services.qdrant.QdrantService"),
        patch("src.runtime.config.GraphConfig.create_llm"),
        patch("src.runtime.config.GraphConfig.create_supervisor_llm"),
    ):
        from telegram_bot.bot import PropertyBot

        return PropertyBot(config)


def _make_message(text="test query"):
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=12345)
    message.chat = MagicMock(id=12345, type="private")
    message.message_id = 100
    message.message_thread_id = None
    message.bot = MagicMock(send_chat_action=AsyncMock())
    message.answer = AsyncMock()
    return message


def _core_result(text: str = "agent response"):
    from src.core import AssistantResult

    return AssistantResult(
        response_text=text,
        route="rag_search",
        request_type="GENERAL",
        request_id="req-test-id-1234",
        retrieved_doc_ids=[],
        retrieved_sources=[],
        documents_count=0,
        latency_ms=10.0,
        cache_hit=False,
        rerank_applied=False,
    )


# ---------------------------------------------------------------------------
# TestQuerySupervisorContentFilter
# ---------------------------------------------------------------------------


class TestQuerySupervisorHandoffMode:
    """Tests for handoff mode check in handle_query (relay or continue)."""

    async def test_handoff_human_mode_relays_and_returns(self):
        """Handoff mode='human' relays message and returns without RAG processing."""
        bot = _create_bot()
        message = _make_message("hello")

        from telegram_bot.services.handoff_state import HandoffData

        handoff_data = HandoffData(client_id=12345, topic_id=999, mode="human")

        handoff_state = AsyncMock()
        handoff_state.get_by_client = AsyncMock(return_value=handoff_data)
        bot._handoff_state = handoff_state

        forum_bridge = AsyncMock()
        forum_bridge.relay_to_topic = AsyncMock()
        bot._forum_bridge = forum_bridge

        await bot.handle_query(message)

        forum_bridge.relay_to_topic.assert_awaited_once_with(
            from_chat_id=12345,
            message_id=100,
            topic_id=999,
        )
        # Should NOT call send_chat_action (returned before that)
        message.bot.send_chat_action.assert_not_awaited()

    async def test_handoff_human_waiting_relays_and_continues(self):
        """Handoff mode='human_waiting' relays AND continues with RAG."""
        bot = _create_bot()
        message = _make_message("hello")

        from telegram_bot.services.handoff_state import HandoffData

        handoff_data = HandoffData(client_id=12345, topic_id=999, mode="human_waiting")

        handoff_state = AsyncMock()
        handoff_state.get_by_client = AsyncMock(return_value=handoff_data)
        bot._handoff_state = handoff_state

        forum_bridge = AsyncMock()
        forum_bridge.relay_to_topic = AsyncMock()
        bot._forum_bridge = forum_bridge

        with patch(
            "telegram_bot.pipeline.supervisor._handle_query_supervisor",
            new_callable=AsyncMock,
        ) as mock_hqs:
            mock_hqs.return_value = "agent response"
            bot._cache = MagicMock()
            bot._cache.redis = None

            await bot.handle_query(message)

        # Relay was called
        forum_bridge.relay_to_topic.assert_awaited_once_with(
            from_chat_id=12345,
            message_id=100,
            topic_id=999,
        )
        # AND module-level _handle_query_supervisor was called (continues processing)
        mock_hqs.assert_awaited_once()

    async def test_handoff_human_mode_relay_failure_falls_back_to_bot_routing(self):
        """Relay failure in 'human' mode logs and falls back to bot routing (#3239)."""
        from aiogram.exceptions import TelegramBadRequest

        from telegram_bot.services.handoff_state import HandoffData

        bot = _create_bot()
        message = _make_message("hello")

        handoff_data = HandoffData(client_id=12345, topic_id=999, mode="human")
        handoff_state = AsyncMock()
        handoff_state.get_by_client = AsyncMock(return_value=handoff_data)
        bot._handoff_state = handoff_state

        forum_bridge = AsyncMock()
        forum_bridge.relay_to_topic = AsyncMock(
            side_effect=TelegramBadRequest(method=None, message="topic closed")
        )
        bot._forum_bridge = forum_bridge

        with patch(
            "telegram_bot.pipeline.supervisor._handle_query_supervisor",
            new_callable=AsyncMock,
        ) as mock_hqs:
            mock_hqs.return_value = "agent response"
            bot._cache = MagicMock()
            bot._cache.redis = None

            await bot.handle_query(message)

        forum_bridge.relay_to_topic.assert_awaited_once()
        # Message must not be swallowed — normal bot routing takes over.
        mock_hqs.assert_awaited_once()

    async def test_handoff_human_waiting_relay_failure_still_continues(self):
        """Relay failure in 'human_waiting' mode logs and continues to RAG (#3239)."""
        from aiogram.exceptions import TelegramBadRequest

        from telegram_bot.services.handoff_state import HandoffData

        bot = _create_bot()
        message = _make_message("hello")

        handoff_data = HandoffData(client_id=12345, topic_id=999, mode="human_waiting")
        handoff_state = AsyncMock()
        handoff_state.get_by_client = AsyncMock(return_value=handoff_data)
        bot._handoff_state = handoff_state

        forum_bridge = AsyncMock()
        forum_bridge.relay_to_topic = AsyncMock(
            side_effect=TelegramBadRequest(method=None, message="topic closed")
        )
        bot._forum_bridge = forum_bridge

        with patch(
            "telegram_bot.pipeline.supervisor._handle_query_supervisor",
            new_callable=AsyncMock,
        ) as mock_hqs:
            mock_hqs.return_value = "agent response"
            bot._cache = MagicMock()
            bot._cache.redis = None

            await bot.handle_query(message)

        forum_bridge.relay_to_topic.assert_awaited_once()
        mock_hqs.assert_awaited_once()

    async def test_no_handoff_proceeds_normally(self):
        """No handoff state proceeds directly to _handle_query_supervisor."""
        bot = _create_bot()
        message = _make_message("hello")
        bot._handoff_state = None

        with patch(
            "telegram_bot.pipeline.supervisor._handle_query_supervisor",
            new_callable=AsyncMock,
        ) as mock_hqs:
            mock_hqs.return_value = "agent response"
            bot._cache = MagicMock()
            bot._cache.redis = None

            await bot.handle_query(message)

        mock_hqs.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestQuerySupervisorSemanticCache
# ---------------------------------------------------------------------------


class TestQuerySupervisorSemanticCache:
    """Cache checks live in the core (#3208): Telegram must not look up."""

    async def test_cache_lookup_not_performed_by_telegram(self):
        """Telegram never calls check_semantic; the core owns the cache stage."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("What is the deposit amount?")

        with (
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=_core_result("core answer"),
            ),
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()
            bot._cache.check_semantic = AsyncMock(return_value="Cached: deposit is 10%")
            bot._send_markdown_chunks = AsyncMock()

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        bot._cache.check_semantic.assert_not_awaited()
        assert result == "core answer"
        message.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestQuerySupervisorCoreEntrypoint
# ---------------------------------------------------------------------------


class TestQuerySupervisorCoreEntrypoint:
    """Tests for the assistant core entrypoint (always active)."""

    async def test_core_entrypoint_called_and_agent_bypassed(self, monkeypatch):
        """Assistant core is the text path: invoke assistant core request and bypass legacy agent."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("What is the cost of Sunny Beach studio?")

        from src.core import AssistantResult

        mock_result = AssistantResult(
            response_text="Sunny Beach studio is 110k EUR.",
            route="rag_search",
            request_type="GENERAL",
            request_id="trace_core",
            retrieved_doc_ids=["sb_studio"],
            retrieved_sources=[{"title": "Sunny Beach Studio", "url": "fixture://sb_studio"}],
            documents_count=1,
            latency_ms=120.0,
            cache_hit=False,
            rerank_applied=True,
        )

        with (
            patch("telegram_bot.bot.classify_query", return_value="GENERAL"),
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_run_core,
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        assert result == "Sunny Beach studio is 110k EUR."
        mock_run_core.assert_awaited_once()
        message.answer.assert_awaited_once()


class TestQuerySupervisorConvergence:
    """One core call; classify/embed/cache are not duplicated in Telegram (#3208)."""

    async def test_single_core_call_no_telegram_classify_embed_cache(self):
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("Сколько стоит студия в Sunny Beach?")

        with (
            patch("telegram_bot.bot.classify_query") as mock_classify,
            patch("telegram_bot.bot.detect_injection") as mock_detect,
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=_core_result("ответ"),
            ) as mock_run_core,
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()
            bot._embeddings = MagicMock()
            bot._embeddings.aembed_query = AsyncMock()

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        assert result == "ответ"
        mock_run_core.assert_awaited_once()
        mock_classify.assert_not_called()
        mock_detect.assert_not_called()
        bot._cache.check_semantic.assert_not_called()
        bot._embeddings.aembed_query.assert_not_awaited()
        # Exactly one send.
        message.answer.assert_awaited_once()

    async def test_filters_propagate_into_core_user_context(self):
        """Deterministic filter extraction still feeds the core request (#3208)."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("Двухкомнатные квартиры в Несебре до 80000 евро")

        with (
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=_core_result("ответ"),
            ) as mock_run_core,
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()
            bot._extract_pre_agent_filters = AsyncMock(return_value={"city": "Несебр"})

            await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        ctx = mock_run_core.await_args.kwargs["user_context"]
        assert ctx.filters == {"city": "Несебр"}

    async def test_cache_hit_result_presented_once(self):
        """Core cache-hit results flow through the same single presentation path."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("What is the deposit amount?")

        cached_result = _core_result("Cached: deposit is 10%")
        cached_result.cache_hit = True
        cached_result.route = "cache_hit"
        cached_result.request_type = "FAQ"

        with (
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=cached_result,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()
            bot._graph_config = MagicMock(show_sources=True)

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        assert result == "Cached: deposit is 10%"
        assert message.answer.await_count == 1

    async def test_trace_metadata_is_truthful_not_hardcoded(self):
        """Grounding/safety trace fields mirror the core result (#3208)."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("Что-то Спросить?")

        core_result = _core_result("ответ")
        core_result.grounded = False
        core_result.safe_fallback_used = True
        core_result.legal_answer_safe = False
        core_result.semantic_cache_safe_reuse = False
        core_result.grounding_mode = "strict"

        meta: dict = {}
        with (
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=core_result,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()
            bot._graph_config = MagicMock(show_sources=False)

            await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata=meta
            )

        assert meta["grounded"] is False
        assert meta["safe_fallback_used"] is True
        assert meta["legal_answer_safe"] is False
        assert meta["semantic_cache_safe_reuse"] is False
        assert meta["grounding_mode"] == "strict"


# ---------------------------------------------------------------------------
# Feedback keyboard identity (post-Langfuse)
# ---------------------------------------------------------------------------


class TestSupervisorFeedbackKeyboard:
    """Core/cache paths attach non-empty callback identity keyboards."""

    async def test_send_core_response_uses_request_id(self):
        from telegram_bot.pipeline.supervisor import _send_core_response

        bot = MagicMock()
        bot._graph_config = MagicMock(show_sources=False)
        bot.bot = MagicMock(send_message=AsyncMock())
        message = MagicMock()
        message.chat = MagicMock(id=1, type="group")
        message.answer = AsyncMock()

        class _Ctx:
            response_sent = False
            history_reply_markup = None

        store = {"request_id": "core-req-id-123456"}
        markup = object()
        with patch("telegram_bot.feedback.build_feedback_keyboard", return_value=markup) as mock_kb:
            await _send_core_response(
                bot,
                message=message,
                response_text="answer body",
                user_text="question",
                query_type="FAQ",
                rag_result_store=store,
                ctx=_Ctx(),
                forum_thread_id=None,
            )

        mock_kb.assert_called_once_with("core-req-id-123456")
        tid = mock_kb.call_args.args[0]
        assert tid and len(tid.encode()) <= 64
        assert message.answer.await_args.kwargs.get("reply_markup") is markup

    async def test_cache_hit_attaches_bounded_identity(self):
        """Cache-hit presentation binds the feedback keyboard to the core request_id."""
        from telegram_bot.pipeline.supervisor import _send_core_response

        bot = MagicMock()
        bot._graph_config = MagicMock(show_sources=False)
        bot.bot = MagicMock(send_message=AsyncMock())
        message = MagicMock()
        message.chat = MagicMock(id=1, type="group")
        message.answer = AsyncMock()

        class _Ctx:
            response_sent = False
            history_reply_markup = None

        store = {"request_id": "core-cache-hit-1234"}
        markup = object()
        with patch("telegram_bot.feedback.build_feedback_keyboard", return_value=markup) as mock_kb:
            await _send_core_response(
                bot,
                message=message,
                response_text="cached answer",
                user_text="question",
                query_type="FAQ",
                rag_result_store=store,
                ctx=_Ctx(),
                forum_thread_id=None,
            )

        mock_kb.assert_called_once_with("core-cache-hit-1234")
        assert message.answer.await_args.kwargs.get("reply_markup") is markup
