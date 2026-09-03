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


class TestQuerySupervisorContentFilter:
    """Tests for the pre-agent content filter guard in _handle_query_supervisor."""

    async def test_injection_hard_mode_blocks(self):
        """Hard mode: detected injection sends blocked response and returns early."""
        config = _make_config(content_filter_enabled=True, guard_mode="hard")
        bot = _create_bot(config)
        message = _make_message("DROP TABLE users;")

        from src.runtime.safety.guard import _BLOCKED_RESPONSE

        with (
            patch("telegram_bot.bot.classify_query", return_value="FAQ"),
            patch(
                "telegram_bot.bot.detect_injection",
                return_value=(True, 0.9, "sql_injection"),
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        assert result == _BLOCKED_RESPONSE
        message.answer.assert_awaited_once_with(_BLOCKED_RESPONSE)

    async def test_injection_soft_mode_continues(self):
        """Soft mode: detected injection logs warning but does not block."""
        config = _make_config(content_filter_enabled=True, guard_mode="soft")
        bot = _create_bot(config)
        message = _make_message("harmless text")

        from src.runtime.safety.guard import _BLOCKED_RESPONSE

        with (
            patch("telegram_bot.bot.classify_query", return_value="CHITCHAT"),
            patch(
                "telegram_bot.bot.detect_injection",
                return_value=(True, 0.7, "prompt_injection"),
            ),
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=_core_result("soft path response"),
            ),
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        for call in message.answer.call_args_list:
            assert call.args[0] != _BLOCKED_RESPONSE
        assert result != _BLOCKED_RESPONSE
        assert result == "soft path response"
        mock_agent_factory.assert_not_called()

    async def test_content_filter_disabled_skips_guard(self):
        """When content_filter_enabled=False, detect_injection is never called."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("DROP TABLE users;")

        with (
            patch("telegram_bot.bot.classify_query", return_value="CHITCHAT"),
            patch("telegram_bot.bot.detect_injection") as mock_detect,
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=_core_result("ok"),
            ),
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")

            await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        mock_detect.assert_not_called()
        mock_agent_factory.assert_not_called()


# ---------------------------------------------------------------------------
# TestQuerySupervisorHandoffMode
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
    """Tests for the pre-agent semantic cache hit/miss in _handle_query_supervisor."""

    async def test_cache_hit_returns_cached_response(self):
        """Cache HIT for cacheable query type returns cached text without invoking agent."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("What is the deposit amount?")

        with (
            patch("telegram_bot.bot.classify_query", return_value="FAQ"),
            patch(
                "telegram_bot.pipeline.supervisor._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch(
                "telegram_bot.pipeline.supervisor.get_query_topic_hint",
                return_value=None,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.get_grounding_mode",
                return_value="default",
            ),
            patch(
                "telegram_bot.pipeline.supervisor.detect_filter_sensitive_query",
            ) as mock_filter_signal,
            patch(
                "telegram_bot.pipeline.supervisor.is_contextual_query",
                return_value=False,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.resolve_semantic_cache_signature",
                return_value=None,
            ),
        ):
            mock_filter_signal.return_value = MagicMock(is_filter_sensitive=False, reasons=[])

            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache.check_semantic = AsyncMock(return_value="Cached: deposit is 10%")
            bot._send_markdown_chunks = AsyncMock()

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        assert result == "Cached: deposit is 10%"
        mock_agent_factory.assert_not_called()
        bot._send_markdown_chunks.assert_awaited_once()


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
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_run_core,
            patch(
                "telegram_bot.pipeline.supervisor.maybe_store_semantic_response",
                new_callable=AsyncMock,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
            patch(
                "telegram_bot.pipeline.supervisor._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.get_query_topic_hint",
                return_value=None,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.get_grounding_mode",
                return_value="default",
            ),
            patch(
                "telegram_bot.pipeline.supervisor.detect_filter_sensitive_query",
                return_value=MagicMock(is_filter_sensitive=False, reasons=[]),
            ),
            patch(
                "telegram_bot.pipeline.supervisor.is_contextual_query",
                return_value=False,
            ),
            patch(
                "telegram_bot.pipeline.supervisor.resolve_semantic_cache_signature",
                return_value=None,
            ),
            patch(
                "telegram_bot.pipeline.supervisor._prepare_pre_agent_retrieval_vectors",
                new_callable=AsyncMock,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache.check_semantic = AsyncMock(return_value=None)

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        assert result == "Sunny Beach studio is 110k EUR."
        mock_run_core.assert_awaited_once()
        mock_agent_factory.assert_not_called()
        message.answer.assert_awaited_once()


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

    async def test_pre_agent_cache_hit_attaches_bounded_identity(self):
        from telegram_bot.pipeline.supervisor import _handle_pre_agent_cache_hit

        bot = MagicMock()
        bot._send_markdown_chunks = AsyncMock()
        message = MagicMock()
        store: dict = {}
        markup = object()

        with patch("telegram_bot.feedback.build_feedback_keyboard", return_value=markup) as mock_kb:
            await _handle_pre_agent_cache_hit(
                bot,
                message=message,
                cached="cached answer",
                user_text="question",
                query_type="FAQ",
                role="client",
                pipeline_start=time.perf_counter(),
                pre_agent_start=time.perf_counter(),
                rag_result_store=store,
                root_trace_metadata=None,
                dense=[0.1, 0.2],
            )

        rid = store.get("request_id")
        assert isinstance(rid, str) and len(rid) == 16
        mock_kb.assert_called_once_with(rid)
        assert bot._send_markdown_chunks.await_args.kwargs.get("reply_markup") is markup
