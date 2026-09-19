"""Tests for _handle_query_supervisor phases (content filter, semantic cache)
and handle_query handoff mode routing.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit._bot_config_factory import make_bot_config as _make_config
from tests.unit._property_bot_factory import make_property_bot


def _make_supervisor_bot(config, **kwargs):
    bot = make_property_bot(config, **kwargs)
    bot.bot.send_message = AsyncMock()
    return bot


@pytest.fixture(autouse=True)
def no_telegram_http(monkeypatch):
    from aiogram.client.session.aiohttp import AiohttpSession

    request = AsyncMock(side_effect=AssertionError("Unexpected Telegram HTTP request"))
    monkeypatch.setattr(AiohttpSession, "make_request", request)
    yield
    request.assert_not_awaited()


@asynccontextmanager
async def _noop_typing(*_args, **_kwargs):
    yield


def _fake_llm_response(text: str, model: str = "gpt-test") -> MagicMock:
    """Build a minimal OpenAI-style completion response (real LLM interface)."""
    choice = SimpleNamespace(message=SimpleNamespace(content=text))
    usage = SimpleNamespace(completion_tokens=10)
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = model
    return resp


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
        bot = _make_supervisor_bot(_make_config())
        message = _make_message("hello")

        from src.services.handoff_state import HandoffData

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
        bot = _make_supervisor_bot(_make_config())
        message = _make_message("hello")

        from src.services.handoff_state import HandoffData

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

        from src.services.handoff_state import HandoffData

        bot = _make_supervisor_bot(_make_config())
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

        from src.services.handoff_state import HandoffData

        bot = _make_supervisor_bot(_make_config())
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
        bot = _make_supervisor_bot(_make_config())
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
        bot = _make_supervisor_bot(config)
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
        bot.bot.send_message.assert_awaited_once()
        message.answer.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestQuerySupervisorCoreEntrypoint
# ---------------------------------------------------------------------------


class TestQuerySupervisorCoreEntrypoint:
    """Tests for the assistant core entrypoint (always active)."""

    async def test_core_entrypoint_called_and_agent_bypassed(self, monkeypatch):
        """Assistant core is the text path: invoke assistant core request and bypass legacy agent."""
        config = _make_config(content_filter_enabled=False)
        bot = _make_supervisor_bot(config)
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
            patch("src.runtime.routing.classify.classify_query", return_value="GENERAL"),
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
        bot.bot.send_message.assert_awaited_once()
        message.answer.assert_not_awaited()

        # #3486: the core must receive the runtime GraphConfig, not BotConfig.
        deps = mock_run_core.await_args.kwargs["dependencies"]
        assert deps.config is bot._graph_config
        assert deps.config is not bot.config
        assert callable(deps.config.create_llm)
        assert callable(deps.config.get_reasoning_kwargs)

    async def test_supervisor_forwards_canonical_locale_code_to_core(self):
        """#3491: the Fluent locale reaches the core as a canonical locale code.

        The supervisor passes the transport-neutral code (not a display label)
        into ``UserContext.language``; an unsupported locale falls back to the
        configured domain language.
        """
        config = _make_config(content_filter_enabled=False)
        bot = _make_supervisor_bot(config)
        message = _make_message("What is included in the complex?")

        with (
            patch(
                "telegram_bot.assistant_core_adapter.run_core_text_request",
                new_callable=AsyncMock,
                return_value=_core_result("core answer"),
            ) as mock_run_core,
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()

            await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="en", root_trace_metadata={}
            )
            supported = mock_run_core.await_args.kwargs["user_context"].language

            await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="xx", root_trace_metadata={}
            )
            unsupported = mock_run_core.await_args.kwargs["user_context"].language

        assert supported == "en"
        # Unsupported locale falls back to the configured domain language.
        assert unsupported == "ru"
        assert config.domain_language == "ru"

    async def test_core_generation_reaches_llm_boundary_with_graph_config(self):
        """Regression #3486: the real supervisor → adapter → core → generation
        chain reaches the substituted LLM boundary on non-empty retrieval.

        Only retrieval (``assistant_pipeline.rag_pipeline``) and the external
        LLM boundary (``GraphConfig.create_llm(...).completion``) are
        substituted; ``run_core_text_request``, ``AssistantApp.run_text`` and
        ``generate_answer`` run for real. With the defect, generation receives
        ``BotConfig`` and the request dies with ``dependency_failed`` before
        any LLM call.
        """
        from src.runtime.config import GraphConfig

        config = _make_config()
        # The real generation chain reads string fields off the runtime config,
        # so this test injects a real GraphConfig instead of the factory mock.
        graph_config = GraphConfig(
            llm_model=config.llm_model,
            redis_url=config.redis_url,
            redis_mode=config.redis_mode,
            domain=config.domain,
        )
        bot = _make_supervisor_bot(config, service_overrides={"graph_config": graph_config})
        message = _make_message("Подскажите варианты студии у моря")

        async def fake_rag_pipeline(**_kwargs):
            return {
                "documents": [
                    {
                        "page_content": "Студия у моря в Солнечном Берегу стоит 110 000 евро.",
                        "metadata": {
                            "source_id": "doc-1",
                            "title": "Studio fact",
                            "url": "fixture://doc-1",
                        },
                    }
                ],
                "cache_hit": False,
                "query_type": "GENERAL",
            }

        llm_spy = MagicMock()
        llm_spy.completion = AsyncMock(
            return_value=_fake_llm_response("Студия у моря стоит 110 000 евро.")
        )

        with (
            patch(
                "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
                new=fake_rag_pipeline,
            ),
            patch(
                "src.runtime.config.GraphConfig.create_llm",
                return_value=llm_spy,
            ) as mock_create_llm,
            patch(
                "telegram_bot.pipeline.supervisor.ChatActionSender.typing",
                side_effect=_noop_typing,
            ),
        ):
            bot._resolve_user_role = AsyncMock(return_value="client")
            bot._cache = MagicMock()
            meta: dict = {}

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata=meta
            )

        # Generation built its LLM from the passed runtime config and reached
        # the external completion boundary exactly once.
        mock_create_llm.assert_called_once()
        llm_spy.completion.assert_awaited_once()
        # The answer is the LLM output (non-empty), not the dependency_failed
        # service-unavailable canned response.
        assert result.strip()
        assert "110 000" in result
        assert meta["query_type"] == "GENERAL"
        assert meta["grounded"] is True


class TestQuerySupervisorConvergence:
    """One core call; classify/embed/cache are not duplicated in Telegram (#3208)."""

    async def test_single_core_call_no_telegram_classify_embed_cache(self):
        config = _make_config(content_filter_enabled=False)
        bot = _make_supervisor_bot(config)
        message = _make_message("Сколько стоит студия в Sunny Beach?")

        with (
            patch("src.runtime.routing.classify.classify_query") as mock_classify,
            patch("src.runtime.safety.guard.detect_injection") as mock_detect,
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
        bot.bot.send_message.assert_awaited_once()
        message.answer.assert_not_awaited()

    async def test_filters_propagate_into_core_user_context(self):
        """Deterministic filter extraction still feeds the core request (#3208)."""
        config = _make_config(content_filter_enabled=False)
        bot = _make_supervisor_bot(config)
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
        bot = _make_supervisor_bot(config)
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
        bot.bot.send_message.assert_awaited_once()
        message.answer.assert_not_awaited()

    async def test_trace_metadata_is_truthful_not_hardcoded(self):
        """Grounding/safety trace fields mirror the core result (#3208)."""
        config = _make_config(content_filter_enabled=False)
        bot = _make_supervisor_bot(config)
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


class TestCoreResponseDelivery:
    """Private responses allocate a draft identity and finalize visible output."""

    def test_draft_id_signed_int32_boundaries(self):
        from telegram_bot.pipeline.streaming import _new_draft_id

        for random_value in (0, 2**31 - 2):
            with patch(
                "telegram_bot.pipeline.streaming.secrets.randbelow", return_value=random_value
            ) as random:
                draft_id = _new_draft_id()
            random.assert_called_once_with(2**31 - 1)
            assert type(draft_id) is int
            assert draft_id == random_value + 1
            assert 1 <= draft_id < 2**31

    async def test_private_response_allocates_id_then_sends_before_marking_sent(self):
        from telegram_bot.pipeline import streaming, supervisor

        ctx = SimpleNamespace(response_sent=False, history_reply_markup=None)
        events = []

        def allocate_id():
            events.append("allocate")
            return streaming._new_draft_id()

        async def send(**kwargs):
            assert ctx.response_sent is False
            events.append(("send", kwargs))

        bot = SimpleNamespace(
            _graph_config=SimpleNamespace(show_sources=False),
            bot=SimpleNamespace(send_message=AsyncMock(side_effect=send)),
        )
        message = _make_message()
        with patch.object(supervisor, "_new_draft_id", side_effect=allocate_id) as draft_id:
            await supervisor._send_core_response(
                bot,
                message=message,
                response_text="answer body",
                user_text="question",
                query_type="FAQ",
                rag_result_store={},
                ctx=ctx,
                forum_thread_id=7,
            )
        draft_id.assert_called_once_with()
        assert events == [
            "allocate",
            (
                "send",
                {
                    "chat_id": 12345,
                    "text": "answer body",
                    "parse_mode": "HTML",
                    "reply_markup": None,
                    "message_thread_id": 7,
                },
            ),
        ]
        assert ctx.response_sent is True
        message.answer.assert_not_awaited()
