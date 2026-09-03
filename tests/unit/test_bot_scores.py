# tests/unit/test_bot_scores.py
"""Bot scores / text-path behavior tests (Langfuse scoring removed #2844/#2969)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.config import BotConfig
from telegram_bot.scoring import compute_checkpointer_overhead_proxy_ms


@pytest.fixture
def mock_config(monkeypatch):
    """Create mock bot config."""
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    return BotConfig(
        _env_file=None,
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
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
    """Create PropertyBot with deps + CallbackData.filter lookup sites mocked."""
    from telegram_bot.bot import PropertyBot

    # Unit conftest may stub aiogram CallbackData / BaseMiddleware as MagicMock.
    _cb_filter = MagicMock(name="CallbackData.filter")
    with (
        patch("telegram_bot.bot.Bot"),
        patch("src.runtime.integrations.cache.CacheLayerManager"),
        patch("src.runtime.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("src.runtime.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("src.runtime.services.qdrant.QdrantService"),
        patch("src.runtime.config.GraphConfig.create_llm"),
        patch("src.runtime.config.GraphConfig.create_supervisor_llm"),
        patch("telegram_bot.bot.setup_throttling_middleware"),
        patch("telegram_bot.bot.setup_error_handler"),
        patch("telegram_bot.bot.FSMCancelMiddleware", MagicMock()),
        patch(
            "telegram_bot.handlers.demo_handler.DemoCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
        patch("telegram_bot.bot.FeedbackCB.filter", create=True, return_value=_cb_filter),
        patch(
            "telegram_bot.bot.FeedbackReasonCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
        patch(
            "telegram_bot.handlers.favorites_callbacks.FavoriteCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
        patch(
            "telegram_bot.handlers.results_callbacks.ResultsCB.filter",
            create=True,
            return_value=_cb_filter,
        ),
    ):
        return PropertyBot(mock_config)


def _make_message(text="квартиры до 100000 евро", user_id=123456789, chat_id=987654321):
    """Create mock Telegram message (non-private chat → message.answer path)."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    # Avoid private draft finalize path (bot.bot.send_message).
    message.chat.type = "group"
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


def _make_typing_cm():
    """Create a mock ChatActionSender.typing() context manager."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=None)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _wire_cache(bot: object) -> AsyncMock:
    """Attach a standard async cache mock used by pre-agent + store paths."""
    cache = AsyncMock()
    cache.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
    cache.get_sparse_embedding = AsyncMock(return_value=None)
    cache.check_semantic = AsyncMock(return_value=None)
    cache.store_embedding = AsyncMock()
    cache.store_semantic = AsyncMock()
    bot._cache = cache  # type: ignore[attr-defined]
    return cache


async def _run_handle_query(
    bot: object,
    message: object,
    *,
    query_type: str,
    store_update: dict | None = None,
    response_text: str = "Answer",
) -> None:
    """Drive handle_query with current supervisor core path mocked."""

    async def _fake_run_core(
        _bot: object,
        _message: object,
        *,
        rag_result_store: dict,
        **_kwargs: object,
    ) -> str:
        if store_update:
            rag_result_store.update(store_update)
        rag_result_store.setdefault("query_type", query_type)
        rag_result_store.setdefault("request_id", "test-request-id")
        return response_text

    with (
        patch("telegram_bot.bot.classify_query", return_value=query_type),
        patch("telegram_bot.bot.detect_injection", return_value=(False, 0.0, None)),
        patch(
            "telegram_bot.pipeline.supervisor._get_or_compute_pre_agent_dense",
            new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ),
        patch(
            "telegram_bot.pipeline.supervisor._prepare_pre_agent_retrieval_vectors",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "telegram_bot.pipeline.supervisor._supervisor_run_core",
            new=AsyncMock(side_effect=_fake_run_core),
        ),
        patch("telegram_bot.pipeline.supervisor.ChatActionSender") as mock_cas,
    ):
        mock_cas.typing.return_value = _make_typing_cm()
        await bot.handle_query(message)  # type: ignore[attr-defined]


def test_compute_checkpointer_overhead_proxy_ms():
    """Unit test for compute_checkpointer_overhead_proxy_ms helper."""
    result = {"latency_stages": {"classify": 0.001, "generate": 0.100}}
    # stages = 101ms, ainvoke wall = 140ms -> proxy overhead = 39ms
    assert compute_checkpointer_overhead_proxy_ms(result, 140.0) == pytest.approx(39.0, abs=0.1)
    # clamp at zero
    assert compute_checkpointer_overhead_proxy_ms(result, 50.0) == 0.0


class TestCreateScoreNoBarId:
    """Regression guard: create_score must use score_id=, never id= (#480)."""

    def test_no_bare_id_kwarg_in_create_score_calls(self):
        """All create_score() calls use score_id= for idempotency, not id=."""
        import ast
        from pathlib import Path

        targets = [
            Path("telegram_bot/scoring.py"),
            Path("telegram_bot/bot.py"),
        ]
        violations = []
        for path in targets:
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # Match *.create_score(...) calls
                if isinstance(func, ast.Attribute) and func.attr == "create_score":
                    for kw in node.keywords:
                        if kw.arg == "id":
                            violations.append(f"{path}:{node.lineno}")
        assert violations == []


class TestTextPathFeedbackButtons:
    """Test feedback buttons and source attribution in text path (#426)."""

    async def test_text_response_has_feedback_keyboard(self, mock_config):
        """Text response should include feedback inline keyboard."""
        bot = _create_bot(mock_config)
        _wire_cache(bot)
        message = _make_message()

        await _run_handle_query(
            bot,
            message,
            query_type="FAQ",
            store_update={
                "query_type": "FAQ",
                "documents": [],
                "response": "Answer",
            },
            response_text="Answer",
        )

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("reply_markup") is not None

    async def test_text_response_has_markdown_parse_mode(self, mock_config):
        """Text response should use HTML parse_mode (Telegram HTML path)."""
        bot = _create_bot(mock_config)
        _wire_cache(bot)
        message = _make_message()

        await _run_handle_query(
            bot,
            message,
            query_type="FAQ",
            store_update={
                "query_type": "FAQ",
                "documents": [],
                "response": "Answer",
            },
            response_text="Answer",
        )

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("parse_mode") == "HTML"

    async def test_chitchat_response_no_feedback_keyboard(self, mock_config):
        """CHITCHAT response should NOT include feedback keyboard."""
        bot = _create_bot(mock_config)
        _wire_cache(bot)
        message = _make_message()

        await _run_handle_query(
            bot,
            message,
            query_type="CHITCHAT",
            store_update={
                "query_type": "CHITCHAT",
                "documents": [],
                "response": "Привет!",
            },
            response_text="Привет!",
        )

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("reply_markup") is None

    async def test_response_without_query_type_has_no_feedback_keyboard(self, mock_config):
        """Response without query_type should NOT include feedback keyboard."""
        bot = _create_bot(mock_config)
        _wire_cache(bot)
        message = _make_message()

        await _run_handle_query(
            bot,
            message,
            query_type="",
            store_update={
                "documents": [],
                "response": "Answer",
            },
            response_text="Answer",
        )

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("reply_markup") is None


class TestTextPathSemanticCacheStore:
    """Test semantic cache persistence in SDK text path."""

    async def test_stores_semantic_cache_for_cacheable_query_type(self, mock_config):
        bot = _create_bot(mock_config)
        cache = _wire_cache(bot)
        message = _make_message("какие документы нужны для покупки квартиры")

        await _run_handle_query(
            bot,
            message,
            query_type="FAQ",
            store_update={
                "query_type": "FAQ",
                "query_embedding": [0.1, 0.2, 0.3],
                "cache_hit": False,
                "documents": [{"text": "doc", "score": 0.9, "metadata": {}}],
                "grade_confidence": 0.9,
                "grounding_mode": "strict",
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "safe_fallback_used": False,
            },
            response_text="Ответ агентом",
        )

        cache.store_semantic.assert_called_once()
        kwargs = cache.store_semantic.call_args.kwargs
        assert kwargs["query"] == message.text
        assert kwargs["response"] == "Ответ агентом"
        assert kwargs["query_type"] == "FAQ"
        assert "user_id" not in kwargs

    async def test_stores_semantic_cache_for_general_type(self, mock_config):
        bot = _create_bot(mock_config)
        cache = _wire_cache(bot)
        message = _make_message("расскажи в целом про рынок")

        await _run_handle_query(
            bot,
            message,
            query_type="GENERAL",
            store_update={
                "query_type": "GENERAL",
                "query_embedding": [0.1, 0.2, 0.3],
                "cache_hit": False,
                "documents": [{"text": "doc", "score": 0.9, "metadata": {}}],
                "grade_confidence": 0.9,
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
            },
            response_text="Ответ агентом",
        )

        cache.store_semantic.assert_called_once()
        kwargs = cache.store_semantic.call_args.kwargs
        assert kwargs["query_type"] == "GENERAL"

    async def test_strict_unsafe_result_skips_text_path_semantic_cache_store(self, mock_config):
        bot = _create_bot(mock_config)
        cache = _wire_cache(bot)
        message = _make_message("какие документы нужны для внж")

        await _run_handle_query(
            bot,
            message,
            query_type="FAQ",
            store_update={
                "query_type": "FAQ",
                "query_embedding": [0.1, 0.2, 0.3],
                "cache_hit": False,
                "documents": [{"text": "doc", "score": 0.9, "metadata": {}}],
                "grade_confidence": 0.9,
                "grounding_mode": "strict",
                "grounded": False,
                "legal_answer_safe": False,
                "semantic_cache_safe_reuse": False,
                "safe_fallback_used": True,
            },
            response_text="Ответ агентом",
        )

        cache.store_semantic.assert_not_called()

    async def test_strict_safe_result_stores_text_path_cache_metadata(self, mock_config):
        bot = _create_bot(mock_config)
        cache = _wire_cache(bot)
        message = _make_message("какие документы нужны для внж")

        await _run_handle_query(
            bot,
            message,
            query_type="FAQ",
            store_update={
                "query_type": "FAQ",
                "query_embedding": [0.1, 0.2, 0.3],
                "cache_hit": False,
                "documents": [{"text": "doc", "score": 0.9, "metadata": {}}],
                "grade_confidence": 0.9,
                "grounding_mode": "strict",
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "safe_fallback_used": False,
            },
            response_text="Ответ агентом",
        )

        cache.store_semantic.assert_called_once()
        metadata = cache.store_semantic.call_args.kwargs["metadata"]
        assert metadata["grounding_mode"] == "strict"
        assert metadata["semantic_cache_safe_reuse"] is True


class TestExtractCurrentTurn:
    """Regression tests for current-turn score isolation (#507)."""

    def test_extracts_messages_after_last_human(self):
        from telegram_bot.bot import _extract_current_turn

        old_human = MagicMock(type="human", content="old question")
        old_ai = MagicMock(type="ai", content="old answer", tool_calls=[])
        current_human = MagicMock(type="human", content="current question")
        current_ai = MagicMock(type="ai", content="current answer", tool_calls=["rag_search"])
        current_tool = MagicMock(type="tool", name="rag_search", content="result")

        all_messages = [old_human, old_ai, current_human, current_ai, current_tool]
        result = _extract_current_turn(all_messages)

        assert len(result) == 3
        assert result[0] is current_human
        assert result[1] is current_ai
        assert result[2] is current_tool

    def test_single_turn_returns_all_messages(self):
        from telegram_bot.bot import _extract_current_turn

        human = MagicMock(type="human", content="question")
        ai = MagicMock(type="ai", content="answer", tool_calls=[])

        result = _extract_current_turn([human, ai])
        assert len(result) == 2

    def test_no_human_message_falls_back_to_all(self):
        from telegram_bot.bot import _extract_current_turn

        ai = MagicMock(type="ai", content="answer", tool_calls=[])
        result = _extract_current_turn([ai])
        assert len(result) == 1

    def test_tool_calls_count_excludes_history(self):
        from telegram_bot.bot import _extract_current_turn

        old_human = MagicMock(type="human")
        old_ai = MagicMock(type="ai", tool_calls=[{"name": "rag_search"}, {"name": "history"}])
        old_tool1 = MagicMock(type="tool", name="rag_search")
        old_tool2 = MagicMock(type="tool", name="history_search")
        old_ai2 = MagicMock(type="ai", tool_calls=[], content="old answer")

        cur_human = MagicMock(type="human")
        cur_ai = MagicMock(type="ai", tool_calls=[{"name": "rag_search"}])
        cur_tool = MagicMock(type="tool", name="rag_search")
        cur_ai2 = MagicMock(type="ai", tool_calls=[], content="current answer")

        all_msgs = [
            old_human,
            old_ai,
            old_tool1,
            old_tool2,
            old_ai2,
            cur_human,
            cur_ai,
            cur_tool,
            cur_ai2,
        ]

        current = _extract_current_turn(all_msgs)
        tool_calls = sum(
            len(m.tool_calls)
            for m in current
            if hasattr(m, "tool_calls") and isinstance(m.tool_calls, list) and m.tool_calls
        )
        assert tool_calls == 1
