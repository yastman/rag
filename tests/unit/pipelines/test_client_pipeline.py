"""Unit tests for telegram_bot/pipelines/client.py."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.pipelines.client import (
    _CONFIDENCE_THRESHOLD,
    _PIPELINE_STORE_TYPES,
    _is_contextual_query,
    detect_agent_intent,
    run_client_pipeline,
)
from telegram_bot.services.types import PipelineResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message() -> MagicMock:
    """Create a mock aiogram Message."""
    msg = MagicMock()
    msg.bot = MagicMock()
    msg.chat = MagicMock(id=12345)
    msg.from_user = MagicMock(id=67890)
    msg.answer = AsyncMock()
    return msg


def _make_config(*, show_sources: bool = False, streaming_enabled: bool = False) -> MagicMock:
    """Create a mock GraphConfig."""
    cfg = MagicMock()
    cfg.show_sources = show_sources
    cfg.streaming_enabled = streaming_enabled
    return cfg


def _make_lf_client() -> MagicMock:
    """Create a no-op Langfuse client mock."""
    lf = MagicMock()
    lf.get_current_trace_id.return_value = ""
    lf.update_current_trace = MagicMock()
    lf.create_score = MagicMock()
    return lf


def _patch_observability(lf_client: MagicMock):
    """Patch get_client to return the given lf_client mock."""
    return patch("telegram_bot.pipelines.client.get_client", return_value=lf_client)


def _patch_rag_pipeline(return_value: dict):
    return patch(
        "telegram_bot.pipelines.client.rag_pipeline",
        new=AsyncMock(return_value=return_value),
    )


def _patch_generate_response(return_value: dict):
    return patch(
        "telegram_bot.pipelines.client.generate_response",
        new=AsyncMock(return_value=return_value),
    )


# ---------------------------------------------------------------------------
# detect_agent_intent
# ---------------------------------------------------------------------------


class TestDetectAgentIntent:
    def test_detect_agent_intent_mortgage(self):
        assert detect_agent_intent("Хочу взять ипотеку") == "mortgage"
        assert detect_agent_intent("Условия кредита") == "mortgage"
        assert detect_agent_intent("Рассрочка на 3 года") == "mortgage"

    def test_detect_agent_intent_handoff(self):
        assert detect_agent_intent("Позвоните мне") == "handoff"
        assert detect_agent_intent("Связаться с менеджером") == "handoff"
        assert detect_agent_intent("Хочу поговорить с менеджером") == "handoff"

    def test_detect_agent_intent_daily_summary(self):
        assert detect_agent_intent("Сделай сводку дня") == "daily_summary"
        assert detect_agent_intent("Итог дня") == "daily_summary"
        assert detect_agent_intent("Отчёт за день") == "daily_summary"

    def test_detect_agent_intent_empty(self):
        assert detect_agent_intent("Какие квартиры есть в центре?") == ""
        assert detect_agent_intent("Цена на однушку") == ""
        assert detect_agent_intent("") == ""


# ---------------------------------------------------------------------------
# _is_contextual_query
# ---------------------------------------------------------------------------


class TestIsContextualQuery:
    def test_contextual_pronouns_detected(self):
        assert _is_contextual_query("расскажи подробнее об этом объекте") is True
        assert _is_contextual_query("первый вариант") is True
        assert _is_contextual_query("а другие есть?") is True

    def test_non_contextual_query(self):
        assert _is_contextual_query("Какие квартиры в центре Москвы?") is False
        assert _is_contextual_query("Цена однокомнатной квартиры") is False


# ---------------------------------------------------------------------------
# run_client_pipeline — CHITCHAT / OFF_TOPIC
# ---------------------------------------------------------------------------


class TestPipelineNonRagPaths:
    async def test_pipeline_chitchat_returns_canned_response(self):
        """CHITCHAT query type returns canned response without calling rag_pipeline."""
        msg = _make_message()
        lf = _make_lf_client()

        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline") as mock_rag,
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="привет",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=MagicMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="CHITCHAT",
            )

        mock_rag.assert_not_called()
        assert isinstance(result, PipelineResult)
        assert result.query_type == "CHITCHAT"
        assert result.response_sent is True
        assert "недвижимост" in result.answer
        msg.answer.assert_called_once()

    async def test_pipeline_off_topic_returns_canned_response(self):
        """OFF_TOPIC query type returns canned response without calling rag_pipeline."""
        msg = _make_message()
        lf = _make_lf_client()

        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline") as mock_rag,
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="расскажи анекдот",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=MagicMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="OFF_TOPIC",
            )

        mock_rag.assert_not_called()
        assert result.query_type == "OFF_TOPIC"
        assert result.response_sent is True
        assert "недвижимост" in result.answer


# ---------------------------------------------------------------------------
# run_client_pipeline — Agent intent gate
# ---------------------------------------------------------------------------


class TestPipelineAgentIntentGate:
    async def test_pipeline_needs_agent_for_mortgage_intent(self):
        """Mortgage keywords trigger needs_agent=True without calling rag_pipeline."""
        msg = _make_message()
        lf = _make_lf_client()

        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline") as mock_rag,
        ):
            result = await run_client_pipeline(
                user_text="хочу взять ипотеку на 20 лет",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=MagicMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="GENERAL",
            )

        mock_rag.assert_not_called()
        msg.answer.assert_not_called()
        assert result.needs_agent is True
        assert result.agent_intent == "mortgage"
        assert result.response_sent is False

    async def test_pipeline_needs_agent_for_handoff_intent(self):
        """Handoff keywords trigger needs_agent=True without calling rag_pipeline."""
        msg = _make_message()
        lf = _make_lf_client()

        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline") as mock_rag,
        ):
            result = await run_client_pipeline(
                user_text="хочу связаться с менеджером",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=MagicMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="GENERAL",
            )

        mock_rag.assert_not_called()
        msg.answer.assert_not_called()
        assert result.needs_agent is True
        assert result.agent_intent == "handoff"


# ---------------------------------------------------------------------------
# run_client_pipeline — Cache hit path
# ---------------------------------------------------------------------------


class TestPipelineCacheHit:
    async def test_pipeline_cache_hit_returns_early(self):
        """When rag_pipeline returns a cache hit, generate_response is NOT called."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "Cached answer",
            "cache_hit": True,
            "documents": [],
            "grade_confidence": 0.0,
            "llm_call_count": 0,
            "latency_stages": {},
        }

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            patch("telegram_bot.pipelines.client.generate_response") as mock_gen,
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="какие документы нужны для ВНЖ?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=MagicMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",
            )

        mock_gen.assert_not_called()
        assert result.answer == "Cached answer"
        assert result.cache_hit is True
        assert result.response_sent is True
        msg.answer.assert_called()


# ---------------------------------------------------------------------------
# run_client_pipeline — Full RAG + generate flow
# ---------------------------------------------------------------------------


class TestPipelineFullFlow:
    async def test_pipeline_rag_and_generate_flow(self):
        """Normal flow: rag_pipeline returns docs, generate_response produces answer."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",  # no cached response
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc 1", "url": "http://x"}, "score": 0.9}],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        gen_result = {
            "response": "Generated answer",
            "response_sent": False,
            "llm_call_count": 1,
        }

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="Какие квартиры в центре?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="GENERAL",
            )

        assert result.answer == "Generated answer"
        assert result.response_sent is True
        assert result.needs_agent is False
        msg.answer.assert_called()

    async def test_pipeline_trace_tags_override_agent_tag(self):
        """update_current_trace must set tags=client_direct, not agent (#566).

        propagate_attributes in bot.py sets tags=["telegram","rag","agent"] before
        the role check, so the client pipeline must override tags to remove "agent".
        """
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        gen_result = {
            "response": "Generated answer",
            "response_sent": False,
            "llm_call_count": 1,
        }

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры в центре?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="GENERAL",
            )

        trace_calls = lf.update_current_trace.call_args_list
        pipeline_call = next(
            (c for c in trace_calls if c.kwargs.get("metadata", {}).get("pipeline_mode")),
            None,
        )
        assert pipeline_call is not None, "update_current_trace with pipeline_mode not found"
        assert pipeline_call.kwargs.get("tags") == ["telegram", "rag", "client_direct"]

    async def test_pipeline_passes_message_to_generate_response(self):
        """generate_response must receive message= so streaming can be enabled (#571)."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        gen_result = {
            "response": "Streamed answer",
            "response_sent": False,
            "llm_call_count": 1,
        }

        mock_gen = AsyncMock(return_value=gen_result)
        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            patch("telegram_bot.pipelines.client.generate_response", mock_gen),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие документы для ВНЖ?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(streaming_enabled=True),
                query_type="FAQ",
            )

        # message= must be forwarded so streaming can activate
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("message") is msg, "message not forwarded to generate_response"

    async def test_pipeline_no_double_send_when_streaming_delivers(self):
        """When streaming delivers the response (response_sent=True), _send_markdown_chunks
        must NOT send the main body again (#571)."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        # Streaming delivered the response — response_sent=True
        gen_result = {
            "response": "Streaming delivered this",
            "response_sent": True,
            "llm_call_count": 1,
        }

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="Какие документы для ВНЖ?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(streaming_enabled=True),
                query_type="FAQ",
            )

        # message.answer() must NOT be called again (streaming already sent)
        msg.answer.assert_not_called()
        assert result.answer == "Streaming delivered this"

    async def test_pipeline_propagates_exception_to_caller(self):
        """When rag_pipeline raises an exception, it propagates to the caller."""
        msg = _make_message()
        lf = _make_lf_client()

        with (
            _patch_observability(lf),
            patch(
                "telegram_bot.pipelines.client.rag_pipeline",
                new=AsyncMock(side_effect=RuntimeError("Qdrant down")),
            ),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            with pytest.raises(RuntimeError, match="Qdrant down"):
                await run_client_pipeline(
                    user_text="Где купить квартиру?",
                    user_id=1,
                    session_id="s1",
                    message=msg,
                    cache=MagicMock(),
                    embeddings=MagicMock(),
                    sparse_embeddings=MagicMock(),
                    qdrant=MagicMock(),
                    reranker=None,
                    llm=None,
                    config=_make_config(),
                    query_type="GENERAL",
                )


# ---------------------------------------------------------------------------
# Cache store guards
# ---------------------------------------------------------------------------


class TestCacheStoreGuards:
    async def test_contextual_query_skips_cache_store(self):
        """Contextual queries (follow-up pronouns) should NOT be stored in cache."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.9,  # above threshold
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
            "query_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "Contextual answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="расскажи подробнее",  # contextual: "подробнее"
                user_id=1,
                session_id="s1",
                message=msg,
                cache=mock_cache,
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",
            )

        mock_cache.store_semantic.assert_not_called()

    async def test_confidence_guard_skips_cache_store(self):
        """Low grade_confidence (<threshold) prevents cache store."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": _CONFIDENCE_THRESHOLD - 0.1,  # below threshold
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
            "query_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "Low confidence answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры продаются?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=mock_cache,
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",
            )

        mock_cache.store_semantic.assert_not_called()

    async def test_empty_documents_skips_cache_store(self):
        """Empty documents list prevents cache store."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [],  # empty
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "No docs answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры продаются?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=mock_cache,
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",
            )

        mock_cache.store_semantic.assert_not_called()

    async def test_cache_store_called_when_all_guards_pass(self):
        """Cache store is called when all guards pass."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": _CONFIDENCE_THRESHOLD + 0.1,  # above threshold
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "Good answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие документы для ВНЖ?",  # no contextual words
                user_id=1,
                session_id="s1",
                message=msg,
                cache=mock_cache,
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",  # in _PIPELINE_STORE_TYPES
            )

        mock_cache.store_semantic.assert_called_once()

    async def test_structured_query_type_skips_cache_store(self):
        """STRUCTURED query type is NOT in _PIPELINE_STORE_TYPES so cache store is skipped."""
        assert "STRUCTURED" not in _PIPELINE_STORE_TYPES
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "Structured answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Найди двушку до 10 млн в Москве",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=mock_cache,
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="STRUCTURED",  # not in _PIPELINE_STORE_TYPES
            )

        mock_cache.store_semantic.assert_not_called()


# ---------------------------------------------------------------------------
# History save
# ---------------------------------------------------------------------------


class TestHistorySave:
    async def test_history_save_called_when_response_available(self):
        """history_service.save_turn() is called when response is generated."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_history = AsyncMock()
        mock_history.save_turn = AsyncMock(return_value=True)

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        gen_result = {"response": "Answer text", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="Какие документы нужны?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",
                history_service=mock_history,
            )

        mock_history.save_turn.assert_called_once_with(
            user_id=1,
            session_id="s1",
            query="Какие документы нужны?",
            response="Answer text",
            input_type="text",
            query_embedding=[0.1, 0.2],
        )
        assert result.answer == "Answer text"

    async def test_history_save_skipped_when_no_history_service(self):
        """history_service.save_turn() is NOT called when history_service=None."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        gen_result = {"response": "Answer text", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="Какие документы нужны?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="FAQ",
                history_service=None,
            )

        assert result.answer == "Answer text"
        assert result.response_sent is True


# ---------------------------------------------------------------------------
# Pre-computed sparse + colbert passthrough (#571)
# ---------------------------------------------------------------------------


class TestPreComputedEmbeddingPassthrough:
    """Verify all three pre-computed embeddings are passed to rag_pipeline (#571)."""

    async def test_passes_sparse_and_colbert_from_rag_result_store(self):
        """pre_computed_sparse and pre_computed_colbert from rag_result_store reach rag_pipeline."""
        msg = _make_message()
        lf = _make_lf_client()

        dense = [0.1] * 1024
        sparse = {"indices": [1], "values": [0.5]}
        colbert = [[0.2] * 1024] * 2

        rag_result = {
            "response": "Есть студии",
            "cache_hit": False,
            "documents": [],
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
        }

        captured_kwargs: dict = {}

        async def _capture_rag(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return rag_result

        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline", side_effect=_capture_rag),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры есть?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="GENERAL",
                rag_result_store={
                    "cache_key_embedding": dense,
                    "cache_key_sparse": sparse,
                    "cache_key_colbert": colbert,
                },
            )

        assert captured_kwargs.get("pre_computed_embedding") == dense
        assert captured_kwargs.get("pre_computed_sparse") == sparse
        assert captured_kwargs.get("pre_computed_colbert") == colbert

    async def test_passes_none_when_embeddings_absent_from_store(self):
        """When rag_result_store lacks sparse/colbert, None is passed to rag_pipeline."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "ok",
            "cache_hit": False,
            "documents": [],
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
        }

        captured_kwargs: dict = {}

        async def _capture_rag(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return rag_result

        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline", side_effect=_capture_rag),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="тест",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(),
                query_type="GENERAL",
                rag_result_store={"cache_key_embedding": [0.1]},
            )

        assert captured_kwargs.get("pre_computed_sparse") is None
        assert captured_kwargs.get("pre_computed_colbert") is None
