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


def _make_config(
    *,
    show_sources: bool = False,
    streaming_enabled: bool = False,
    relevance_threshold_rrf: float = _CONFIDENCE_THRESHOLD,
) -> MagicMock:
    """Create a mock GraphConfig."""
    cfg = MagicMock()
    cfg.show_sources = show_sources
    cfg.streaming_enabled = streaming_enabled
    cfg.relevance_threshold_rrf = relevance_threshold_rrf
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

    def test_detect_agent_intent_apartment(self):
        assert detect_agent_intent("хочу двушку с видом на море") == "apartment"
        assert detect_agent_intent("подобрать квартиру") == "apartment"
        assert detect_agent_intent("студия до 80000") == "apartment"
        assert detect_agent_intent("трёхкомнатная квартира") == "apartment"
        assert detect_agent_intent("апартаменты в Несебре") == "apartment"

    def test_detect_agent_intent_empty(self):
        assert detect_agent_intent("как оформить ВНЖ") == ""
        assert detect_agent_intent("какие документы нужны") == ""
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
        lf.get_current_trace_id.return_value = "trace-123"

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

    async def test_pipeline_metadata_includes_pre_agent_and_e2e_latency(self):
        """Trace metadata should include pre-agent and canonical end-to-end latency."""
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
        rag_store = {"pre_agent_ms": 120.0}

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
                rag_result_store=rag_store,
            )

        trace_calls = lf.update_current_trace.call_args_list
        pipeline_call = next(
            (c for c in trace_calls if c.kwargs.get("metadata", {}).get("pipeline_mode")),
            None,
        )
        assert pipeline_call is not None
        metadata = pipeline_call.kwargs["metadata"]
        assert metadata["pre_agent_ms"] == 120.0
        assert metadata["e2e_latency_ms"] >= metadata["pipeline_wall_ms"]
        assert rag_store["e2e_latency_ms"] >= rag_store["pipeline_wall_ms"]

    async def test_pipeline_metadata_includes_route_topic_and_grounding_contract(self):
        """Client-direct trace metadata should expose route/topic/grounding fields early."""
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
            "topic_hint": "legal",
        }
        gen_result = {
            "response": "Generated answer",
            "response_sent": False,
            "llm_call_count": 1,
            "grounding_mode": "strict",
        }

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие документы нужны для ВНЖ?",
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
            )

        trace_calls = lf.update_current_trace.call_args_list
        pipeline_call = next(
            (c for c in trace_calls if c.kwargs.get("metadata", {}).get("pipeline_mode")),
            None,
        )
        assert pipeline_call is not None
        metadata = pipeline_call.kwargs["metadata"]
        assert metadata["route"] == "client_direct"
        assert metadata["pipeline_mode"] == "client_direct"
        assert metadata["query_type"] == "FAQ"
        assert metadata["topic_hint"] == "legal"
        assert metadata["grounding_mode"] == "strict"

    async def test_pipeline_passes_strict_grounding_mode_to_generate_response(self):
        """Legal topic should force strict grounding mode in generation step."""
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
            "topic_hint": "legal",
        }
        gen_result = {
            "response": "Нужна проверка менеджером.",
            "response_sent": False,
            "llm_call_count": 0,
            "grounding_mode": "strict",
            "safe_fallback_used": True,
            "grounded": False,
        }

        captured_kwargs: dict = {}

        async def _capture_generate(**kwargs):
            captured_kwargs.update(kwargs)
            return gen_result

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            patch("telegram_bot.pipelines.client.generate_response", side_effect=_capture_generate),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="Какие документы нужны для ВНЖ?",
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
            )

        assert captured_kwargs["grounding_mode"] == "strict"
        assert result.answer == "Нужна проверка менеджером."

    async def test_pipeline_shows_sources_for_strict_grounding_even_when_global_sources_disabled(
        self,
    ):
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"text": "Документ", "score": 0.82, "metadata": {"title": "ВНЖ"}}],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "topic_hint": "legal",
        }
        gen_result = {
            "response": "Подтвержденный ответ.",
            "response_sent": False,
            "llm_call_count": 1,
            "grounding_mode": "strict",
            "safe_fallback_used": False,
            "grounded": True,
        }
        send_chunks = AsyncMock()

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client._send_markdown_chunks", send_chunks),
            patch(
                "telegram_bot.pipelines.client.format_sources",
                return_value="\n\nИсточники:\n[1] ВНЖ",
            ),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            result = await run_client_pipeline(
                user_text="Какие документы нужны для ВНЖ?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=AsyncMock(),
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(show_sources=False),
                query_type="FAQ",
            )

        assert result.answer == "Подтвержденный ответ."
        send_text = send_chunks.await_args.args[1]
        assert "Подтвержденный ответ." in send_text
        assert "Источники:" in send_text

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

    async def test_pipeline_passes_semantic_cache_already_checked_to_rag_pipeline(self):
        msg = _make_message()
        lf = _make_lf_client()

        rag_result = {
            "response": "Cached-ish",
            "cache_hit": False,
            "documents": [],
            "grade_confidence": 0.0,
            "llm_call_count": 0,
            "latency_stages": {},
        }
        rag_store = {"semantic_cache_already_checked": True}

        mock_rag = AsyncMock(return_value=rag_result)
        with (
            _patch_observability(lf),
            patch("telegram_bot.pipelines.client.rag_pipeline", mock_rag),
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
                rag_result_store=rag_store,
            )

        assert mock_rag.await_args.kwargs["semantic_cache_already_checked"] is True

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
                user_text="Какие квартиры в Несебре?",
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

    async def test_rrf_level_confidence_allows_cache_store(self):
        """RRF-scale confidence should still allow semantic cache write."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.0167}],
            "grade_confidence": 0.0167,
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
            "query_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "RRF answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры в Несебре?",
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

        assert _CONFIDENCE_THRESHOLD <= 0.0167
        mock_cache.store_semantic.assert_called_once()

    async def test_cache_store_uses_config_relevance_threshold(self):
        """Cache store guard should use config.relevance_threshold_rrf as source of truth."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.02}],
            "grade_confidence": 0.02,
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
            "query_embedding": [0.1, 0.2, 0.3],
        }
        gen_result = {"response": "Config threshold answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры доступны?",
                user_id=1,
                session_id="s1",
                message=msg,
                cache=mock_cache,
                embeddings=MagicMock(),
                sparse_embeddings=MagicMock(),
                qdrant=MagicMock(),
                reranker=None,
                llm=None,
                config=_make_config(relevance_threshold_rrf=0.03),
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

    async def test_structured_query_type_stores_cache(self):
        """STRUCTURED query type is in _PIPELINE_STORE_TYPES, so cache store is enabled."""
        assert "STRUCTURED" in _PIPELINE_STORE_TYPES
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
                user_text="Найди объект до 10 млн в Москве",
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
                query_type="STRUCTURED",
            )

        mock_cache.store_semantic.assert_called_once()


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

    async def test_passes_state_contract_from_rag_result_store(self):
        """run_client_pipeline should pass shared pre-agent state_contract downstream."""
        msg = _make_message()
        lf = _make_lf_client()

        state_contract = {
            "cache_checked": True,
            "cache_hit": False,
            "cache_scope": "rag",
            "embedding_bundle_ready": True,
            "embedding_bundle_version": "bge_m3_hybrid_colbert",
            "dense_vector": [0.1] * 3,
            "sparse_vector": {"indices": [1], "values": [0.5]},
            "colbert_query": [[0.2] * 3],
            "query_type": "GENERAL",
            "topic_hint": "legal",
            "retrieval_policy": "topic_then_relax",
            "grounding_mode": "strict",
        }
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
                query_type="GENERAL",
                rag_result_store={"state_contract": state_contract},
            )

        assert captured_kwargs.get("state_contract") == state_contract

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


# ---------------------------------------------------------------------------
# Task 3: Additional cache store guard keyword coverage
# ---------------------------------------------------------------------------


class TestContextualKeywordCoverage:
    """Verify specific contextual keywords trigger cache-store skip."""

    def test_este_pronoun_skips_cache_store(self):
        """'это' (demonstrative pronoun) is a contextual follow-up."""
        assert _is_contextual_query("это правильный вариант?") is True

    def test_esho_adverb_skips_cache_store(self):
        """'ещё' (still / more) marks a contextual follow-up."""
        assert _is_contextual_query("ещё варианты есть?") is True

    def test_oni_pronoun_is_contextual(self):
        """'они' (they) references prior items — contextual."""
        assert _is_contextual_query("они уже проданы?") is True

    def test_tot_zhe_phrase_is_contextual(self):
        """'тот же' (the same) references previous context."""
        assert _is_contextual_query("это тот же объект?") is True

    def test_plain_question_without_context_markers_is_not_contextual(self):
        """Questions without contextual pronouns are not follow-ups."""
        assert _is_contextual_query("Квартиры в центре Москвы") is False
        assert _is_contextual_query("Сколько стоит однокомнатная?") is False


class TestCacheStoreGuardMissingVector:
    """Verify cache store is skipped when store_vector is absent or invalid."""

    async def test_none_cache_key_embedding_skips_cache_store(self):
        """When neither cache_key_embedding nor query_embedding is present, skip store."""
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
            # No cache_key_embedding or query_embedding → store_vector will be None
        }
        gen_result = {"response": "Answer", "response_sent": False}

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            _patch_generate_response(gen_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие квартиры?",
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

    async def test_cache_hit_skips_cache_store(self):
        """Cache hit path does not re-store the same response."""
        msg = _make_message()
        lf = _make_lf_client()
        mock_cache = AsyncMock()

        rag_result = {
            "response": "Hit response",
            "cache_hit": True,
            "documents": [{"metadata": {"title": "Doc"}, "score": 0.9}],
            "grade_confidence": 0.9,
            "llm_call_count": 0,
            "latency_stages": {},
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }

        with (
            _patch_observability(lf),
            _patch_rag_pipeline(rag_result),
            patch("telegram_bot.pipelines.client.write_langfuse_scores"),
            patch("telegram_bot.pipelines.client.score"),
        ):
            await run_client_pipeline(
                user_text="Какие объекты?",
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


class TestDetectAgentIntentEdgeCases:
    """Verify keyword matching details and case insensitivity."""

    def test_uppercase_mortgage_keyword_detected(self):
        """Mortgage detection is case-insensitive (text.lower() applied)."""
        assert detect_agent_intent("ИПОТЕКА на 20 лет") == "mortgage"

    def test_позвонить_triggers_handoff(self):
        """'позвонить' contains the 'позвон' keyword — maps to handoff."""
        assert detect_agent_intent("хочу позвонить менеджеру") == "handoff"

    def test_рассрочка_triggers_mortgage(self):
        """'рассрочка' contains 'рассрочк' — maps to mortgage."""
        assert detect_agent_intent("есть ли рассрочка?") == "mortgage"

    def test_итоги_дня_triggers_daily_summary(self):
        """'итоги дня' (plural) maps to daily_summary."""
        assert detect_agent_intent("покажи итоги дня") == "daily_summary"


# ---------------------------------------------------------------------------
# Task 4: PipelineResult dataclass invariants (telegram_bot/services/types.py)
# ---------------------------------------------------------------------------


class TestPipelineResultFrozenInvariants:
    """Verify PipelineResult is an immutable frozen dataclass with slots."""

    def test_frozen_raises_on_field_assignment(self):
        """Assigning to any field after construction must raise FrozenInstanceError."""
        from dataclasses import FrozenInstanceError

        result = PipelineResult(answer="test")
        with pytest.raises(FrozenInstanceError):
            result.answer = "modified"  # type: ignore[misc]

    def test_frozen_raises_on_new_attribute(self):
        """Setting a non-existent attribute must also be rejected (slots=True)."""
        result = PipelineResult()
        with pytest.raises((AttributeError, TypeError)):
            result.new_field = "value"  # type: ignore[attr-defined]

    def test_uses_slots(self):
        """slots=True should add __slots__ to the class."""
        assert hasattr(PipelineResult, "__slots__")


class TestPipelineResultDefaultValues:
    """Verify all default field values match the documented contract."""

    def test_answer_defaults_to_empty_string(self):
        assert PipelineResult().answer == ""

    def test_query_type_defaults_to_general(self):
        assert PipelineResult().query_type == "GENERAL"

    def test_cache_hit_defaults_to_false(self):
        assert PipelineResult().cache_hit is False

    def test_needs_agent_defaults_to_false(self):
        assert PipelineResult().needs_agent is False

    def test_agent_intent_defaults_to_empty_string(self):
        assert PipelineResult().agent_intent == ""

    def test_latency_ms_defaults_to_zero(self):
        assert PipelineResult().latency_ms == 0.0

    def test_llm_call_count_defaults_to_zero(self):
        assert PipelineResult().llm_call_count == 0

    def test_pipeline_mode_defaults_to_client_direct(self):
        assert PipelineResult().pipeline_mode == "client_direct"

    def test_response_sent_defaults_to_false(self):
        assert PipelineResult().response_sent is False

    def test_sent_message_defaults_to_none(self):
        assert PipelineResult().sent_message is None

    def test_sources_defaults_to_empty_list(self):
        assert PipelineResult().sources == []

    def test_scores_defaults_to_empty_dict(self):
        assert PipelineResult().scores == {}


class TestPipelineResultNeedsAgentFlag:
    """Verify needs_agent flag semantics in context of pipeline routing."""

    def test_needs_agent_true_with_intent(self):
        """needs_agent=True with agent_intent set — signals agent routing required."""
        result = PipelineResult(needs_agent=True, agent_intent="mortgage")
        assert result.needs_agent is True
        assert result.agent_intent == "mortgage"

    def test_needs_agent_false_with_full_answer(self):
        """Normal pipeline result has needs_agent=False and an answer."""
        result = PipelineResult(
            answer="Here is the answer",
            needs_agent=False,
            response_sent=True,
        )
        assert result.needs_agent is False
        assert result.answer == "Here is the answer"

    def test_sources_list_is_independent_per_instance(self):
        """Each PipelineResult instance gets its own sources list (default_factory)."""
        r1 = PipelineResult()
        r2 = PipelineResult()
        assert r1.sources is not r2.sources

    def test_scores_dict_is_independent_per_instance(self):
        """Each PipelineResult instance gets its own scores dict (default_factory)."""
        r1 = PipelineResult()
        r2 = PipelineResult()
        assert r1.scores is not r2.scores


# ---------------------------------------------------------------------------
# Streaming feedback keyboard (#745)
# ---------------------------------------------------------------------------


class TestStreamingFeedbackKeyboard:
    """When streaming delivers the response, feedback keyboard must still
    be attached via edit_message_reply_markup (#745)."""

    async def test_streaming_attaches_feedback_keyboard_via_edit(self):
        """After streaming (response_sent=True), edit_message_reply_markup
        is called on the sent message to attach the feedback keyboard."""
        msg = _make_message()
        msg.bot.edit_message_reply_markup = AsyncMock()
        lf = _make_lf_client()
        lf.get_current_trace_id.return_value = "trace-abc-123"

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
            "response_sent": True,
            "sent_message": {"chat_id": 12345, "message_id": 99},
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
                user_text="Какие квартиры в Несебре?",
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

        # message.answer must NOT be called (streaming already sent)
        msg.answer.assert_not_called()
        # edit_message_reply_markup must be called to attach feedback keyboard
        msg.bot.edit_message_reply_markup.assert_called_once()
        call_kwargs = msg.bot.edit_message_reply_markup.call_args
        assert call_kwargs.kwargs["chat_id"] == 12345
        assert call_kwargs.kwargs["message_id"] == 99
        assert call_kwargs.kwargs["reply_markup"] is not None

    async def test_streaming_no_sent_message_ref_skips_edit(self):
        """When streaming delivers but sent_message ref is missing,
        edit_message_reply_markup is not called (graceful degradation)."""
        msg = _make_message()
        msg.bot.edit_message_reply_markup = AsyncMock()
        lf = _make_lf_client()
        lf.get_current_trace_id.return_value = "trace-abc-456"

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
            "response_sent": True,
            # No sent_message — streaming failed to capture ref
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
                user_text="Какие квартиры в Несебре?",
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

        # Neither answer nor edit should be called
        msg.answer.assert_not_called()
        msg.bot.edit_message_reply_markup.assert_not_called()

    async def test_streaming_with_sources_sends_sources_with_keyboard(self):
        """When streaming + sources enabled, sources are sent as a separate
        message with the feedback keyboard (existing behavior preserved)."""
        msg = _make_message()
        msg.bot.edit_message_reply_markup = AsyncMock()
        lf = _make_lf_client()
        lf.get_current_trace_id.return_value = "trace-abc-789"

        rag_result = {
            "response": "",
            "cache_hit": False,
            "documents": [
                {"metadata": {"title": "Doc1", "source": "file1.pdf"}, "score": 0.9},
            ],
            "grade_confidence": 0.7,
            "llm_call_count": 0,
            "latency_stages": {},
            "query_embedding": [0.1, 0.2],
            "cache_key_embedding": [0.1, 0.2],
        }
        gen_result = {
            "response": "Streamed answer",
            "response_sent": True,
            "sent_message": {"chat_id": 12345, "message_id": 99},
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
                config=_make_config(streaming_enabled=True, show_sources=True),
                query_type="FAQ",
            )

        # Sources sent via message.answer (with keyboard), not via edit
        msg.answer.assert_called()
        msg.bot.edit_message_reply_markup.assert_not_called()
