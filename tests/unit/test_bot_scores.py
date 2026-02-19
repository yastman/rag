# tests/unit/test_bot_scores.py
"""Tests for Langfuse score writing (#310: scoring logic moved to scoring.py)."""

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.config import BotConfig
from telegram_bot.scoring import compute_checkpointer_overhead_proxy_ms, write_langfuse_scores


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
    """Create PropertyBot with all deps mocked."""
    from telegram_bot.bot import PropertyBot

    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        bot = PropertyBot(mock_config)
    return bot  # noqa: RET504


def _make_message(text="квартиры до 100000 евро", user_id=123456789, chat_id=987654321):
    """Create mock Telegram message."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.answer = AsyncMock()
    return message


def _make_voice_message(user_id=123456789, chat_id=987654321):
    """Create mock Telegram voice message."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.bot.get_file = AsyncMock()

    # download_file writes bytes into the destination buffer (like real aiogram)
    async def _fake_download(file_path, destination):
        destination.write(b"fake-ogg-audio-data")

    message.bot.download_file = AsyncMock(side_effect=_fake_download)
    message.voice = MagicMock()
    message.voice.file_id = "file123"
    message.voice.duration = 5
    file_mock = MagicMock()
    file_mock.file_path = "voice/file.ogg"
    message.bot.get_file.return_value = file_mock
    return message


def _make_typing_cm():
    """Create a mock ChatActionSender.typing() context manager.

    __aexit__ returns False by default so exceptions propagate normally.
    """
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock()
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


_TEST_TRACE_ID = "test-trace-abc-123"


def _run_score_writer(result, mock_lf):
    """Call write_langfuse_scores directly for unit testing scoring logic.

    Since #310, pipeline scores are written by scoring.py (called from rag_agent tool
    and handle_voice). This helper tests the scoring function in isolation.
    Uses explicit trace_id (#435) — create_score with idempotency keys.
    """
    if not hasattr(mock_lf, "get_current_trace_id") or not callable(
        getattr(mock_lf, "get_current_trace_id", None)
    ):
        mock_lf.get_current_trace_id = MagicMock(return_value=_TEST_TRACE_ID)
    write_langfuse_scores(mock_lf, result, trace_id=_TEST_TRACE_ID)
    return mock_lf


def _mock_agent_result(**overrides):
    """Create a standard SDK agent result dict (#413)."""
    base = {
        "messages": [MagicMock(content="Supervisor response")],
    }
    base.update(overrides)
    return base


async def _run_handle_query_supervisor(mock_config, mock_lf_client, *, history_service=None):
    """Run handle_query through SDK agent path with mocked agent (#413)."""
    bot = _create_bot(mock_config)
    if history_service is not None:
        bot._history_service = history_service

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value=_mock_agent_result())

    with (
        patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
        patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
        patch("telegram_bot.bot.propagate_attributes"),
        patch("telegram_bot.bot.create_callback_handler", return_value=None),
    ):
        message = _make_message()
        with patch("telegram_bot.bot.ChatActionSender") as mock_cas:
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

    return mock_lf_client, bot


# Typical graph result for a full RAG pipeline (cache miss, search, rerank, generate)
FULL_PIPELINE_RESULT = {
    "response": "Вот квартиры до 100000 евро...",
    "query_type": "STRUCTURED",
    "cache_hit": False,
    "cached_response": None,
    "search_results_count": 5,
    "rerank_applied": True,
    "documents_relevant": True,
    "embeddings_cache_hit": False,
    "search_cache_hit": False,
    "grade_confidence": 0.85,
    "pipeline_wall_ms": 862.0,
    "latency_stages": {
        "classify": 0.001,
        "cache_check": 0.050,
        "retrieve": 0.200,
        "grade": 0.001,
        "rerank": 0.100,
        "generate": 0.500,
        "respond": 0.010,
    },
    # Latency breakdown (#147)
    "llm_ttft_ms": 150.0,
    "llm_response_duration_ms": 450.0,
    "llm_decode_ms": 300.0,
    "llm_tps": 42.5,
    "llm_queue_ms": None,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": True,
    # Response length control (#129)
    "response_style": "balanced",
    "response_difficulty": "medium",
    "response_style_reasoning": "length_heuristic",
    "answer_words": 12,
    "answer_chars": 65,
    "answer_to_question_ratio": 2.4,
    "response_policy_mode": "enforced",
    # Source attribution (#225)
    "sources_count": 3,
    # Conversation memory (#154)
    "messages": [
        {"role": "user", "content": "query"},
        {"role": "assistant", "content": "response"},
    ],
}

# Cache hit result (short-circuit)
CACHE_HIT_RESULT = {
    "response": "Cached answer here",
    "query_type": "GENERAL",
    "cache_hit": True,
    "cached_response": "Cached answer here",
    "search_results_count": 0,
    "rerank_applied": False,
    "documents_relevant": False,
    "latency_stages": {
        "classify": 0.001,
        "cache_check": 0.020,
        "respond": 0.005,
    },
    "llm_decode_ms": None,
    "llm_tps": None,
    "llm_queue_ms": None,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": False,
    "messages": [{"role": "user", "content": "query"}],
}

# Chitchat result (no RAG at all)
CHITCHAT_RESULT = {
    "response": "Привет! 👋 Я помогу найти недвижимость.",
    "query_type": "CHITCHAT",
    "cache_hit": False,
    "search_results_count": 0,
    "rerank_applied": False,
    "latency_stages": {"classify": 0.001, "respond": 0.005},
    "llm_decode_ms": None,
    "llm_tps": None,
    "llm_queue_ms": None,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": False,
    "messages": [],
}


class TestScoreWriting:
    """Test that write_langfuse_scores writes correct scores from result state."""

    def test_scores_written_full_pipeline(self):
        """All scores should be written for a full pipeline result."""
        mock_lf = MagicMock()
        result = {**FULL_PIPELINE_RESULT, "checkpointer_overhead_proxy_ms": 39.0}
        _run_score_writer(result, mock_lf)

        score_calls = mock_lf.create_score.call_args_list
        score_names = [call.kwargs["name"] for call in score_calls]

        expected_names = [
            "query_type",
            "latency_total_ms",
            "semantic_cache_hit",
            "embeddings_cache_hit",
            "search_cache_hit",
            "rerank_applied",
            "rerank_cache_hit",
            "results_count",
            "no_results",
            "llm_used",
            "confidence_score",
            "hyde_used",
            "llm_ttft_ms",
            "llm_response_duration_ms",
            "streaming_enabled",
            "llm_timeout",
            "llm_stream_recovery",
            "llm_decode_ms",
            "llm_tps",
            "llm_queue_unavailable",
            "answer_words",
            "answer_chars",
            "answer_to_question_ratio",
            "response_style_applied",
            "input_type",
            "bge_embed_error",
            "bge_embed_latency_ms",
            # Prompt injection defense (#226)
            "security_alert",
            "guard_ml_available",
            # Source attribution (#225)
            "sources_shown",
            "sources_count",
            # Conversation memory (#159)
            "memory_messages_count",
            "summarization_triggered",
            "checkpointer_overhead_proxy_ms",
        ]
        assert sorted(score_names) == sorted(expected_names)
        assert mock_lf.create_score.call_count == 34

    def test_score_values_full_pipeline(self):
        """Score values should match the graph result state."""
        mock_lf = MagicMock()
        _run_score_writer(FULL_PIPELINE_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.create_score.call_args_list
        }
        assert scores["query_type"] == 2.0
        assert scores["semantic_cache_hit"] == 0.0
        assert scores["rerank_applied"] == 1.0
        assert scores["results_count"] == 5.0
        assert scores["no_results"] == 0.0
        assert scores["llm_used"] == 1.0
        assert abs(scores["latency_total_ms"] - FULL_PIPELINE_RESULT["pipeline_wall_ms"]) < 0.01
        assert scores["embeddings_cache_hit"] == 0.0
        assert scores["search_cache_hit"] == 0.0
        assert scores["confidence_score"] == 0.85
        assert scores["answer_words"] == 12.0
        assert scores["answer_chars"] == 65.0
        assert scores["answer_to_question_ratio"] == 2.4
        assert scores["response_style_applied"] == 1.0

    @pytest.mark.parametrize(
        ("result_fixture", "expected_scores"),
        [
            (
                "CACHE_HIT_RESULT",
                {
                    "semantic_cache_hit": 1.0,
                    "llm_used": 0.0,
                    "rerank_applied": 0.0,
                    "results_count": 0.0,
                },
            ),
            (
                "CHITCHAT_RESULT",
                {"query_type": 0.0, "llm_used": 0.0, "results_count": 0.0, "no_results": 1.0},
            ),
        ],
        ids=["cache_hit", "chitchat"],
    )
    def test_score_values_by_result_type(self, result_fixture, expected_scores):
        """Score values should match per result type (cache hit, chitchat)."""
        mock_lf = MagicMock()
        result_data = {"CACHE_HIT_RESULT": CACHE_HIT_RESULT, "CHITCHAT_RESULT": CHITCHAT_RESULT}[
            result_fixture
        ]
        _run_score_writer(result_data, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.create_score.call_args_list
        }
        for name, expected_value in expected_scores.items():
            assert scores[name] == expected_value, f"{name}: {scores[name]} != {expected_value}"

    @pytest.mark.parametrize(
        ("result_override", "test_id"),
        [
            ({"response_policy_mode": "shadow", "response_style": "short"}, "shadow_mode"),
            ({"response_style": ""}, "empty_style_no_policy"),
        ],
        ids=["shadow_mode", "empty_style_no_policy"],
    )
    def test_style_applied_not_emitted(self, result_override, test_id):
        """response_style_applied must NOT be emitted in shadow/non-enforced paths."""
        mock_lf = MagicMock()
        base = FULL_PIPELINE_RESULT if "shadow" in test_id else CACHE_HIT_RESULT
        result = {**base, **result_override}
        _run_score_writer(result, mock_lf)

        score_names = [c.kwargs["name"] for c in mock_lf.create_score.call_args_list]
        assert "response_style_applied" not in score_names

    def test_scores_written_even_on_null_client(self):
        """When Langfuse disabled, _NullLangfuseClient.create_score is called (no-op, #435)."""
        from telegram_bot.observability import _NullLangfuseClient

        mock_lf = _NullLangfuseClient()
        # _NullLangfuseClient.get_current_trace_id() returns "" → write_langfuse_scores
        # returns early. Pass explicit trace_id to exercise the scoring code path.
        write_langfuse_scores(mock_lf, FULL_PIPELINE_RESULT, trace_id="null-trace")


class TestLatencyBreakdownScores:
    """Test latency breakdown score writing (#147)."""

    def test_streaming_path_writes_numeric_and_boolean_scores(self):
        """Streaming: writes llm_decode_ms, llm_tps as NUMERIC; boolean flags."""
        mock_lf = MagicMock()
        _run_score_writer(FULL_PIPELINE_RESULT, mock_lf)

        calls = mock_lf.create_score.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        assert score_map["llm_decode_ms"]["value"] == 300.0
        assert score_map["llm_tps"]["value"] == 42.5
        assert score_map["streaming_enabled"]["value"] == 1
        assert score_map["streaming_enabled"]["data_type"] == "BOOLEAN"
        assert score_map["llm_timeout"]["value"] == 0
        assert score_map["llm_timeout"]["data_type"] == "BOOLEAN"
        assert score_map["llm_stream_recovery"]["value"] == 0
        assert score_map["llm_stream_recovery"]["data_type"] == "BOOLEAN"
        assert score_map["llm_queue_unavailable"]["value"] == 1
        assert score_map["llm_queue_unavailable"]["data_type"] == "BOOLEAN"
        assert "llm_decode_unavailable" not in score_map

    def test_non_streaming_writes_unavailable_flags(self):
        """Non-streaming: writes *_unavailable BOOLEAN flags, skips NUMERIC decode/tps."""
        mock_lf = MagicMock()
        _run_score_writer(CACHE_HIT_RESULT, mock_lf)

        calls = mock_lf.create_score.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        assert "llm_decode_ms" not in score_map
        assert "llm_tps" not in score_map
        assert "llm_queue_ms" not in score_map
        assert score_map["llm_decode_unavailable"]["value"] == 1
        assert score_map["llm_decode_unavailable"]["data_type"] == "BOOLEAN"
        assert score_map["llm_tps_unavailable"]["value"] == 1
        assert score_map["llm_queue_unavailable"]["value"] == 1
        assert score_map["streaming_enabled"]["value"] == 0
        assert score_map["streaming_enabled"]["data_type"] == "BOOLEAN"

    def test_hard_fail_writes_timeout_true(self):
        """Hard LLM failure: llm_timeout=1 BOOLEAN."""
        mock_lf = MagicMock()
        timeout_result = {
            **CHITCHAT_RESULT,
            "llm_timeout": True,
            "llm_stream_recovery": False,
            "streaming_enabled": False,
            "llm_decode_ms": None,
            "llm_tps": None,
            "llm_queue_ms": None,
        }
        _run_score_writer(timeout_result, mock_lf)

        calls = mock_lf.create_score.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        assert score_map["llm_timeout"]["value"] == 1
        assert score_map["llm_timeout"]["data_type"] == "BOOLEAN"


async def _run_handle_voice(mock_config, graph_result, mock_lf_client):
    """Shared helper: run handle_voice with mocked graph and Langfuse client."""
    bot = _create_bot(mock_config)
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value=graph_result)

    with (
        patch("telegram_bot.bot.build_graph", return_value=mock_graph),
        patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
        patch("telegram_bot.bot.propagate_attributes") as mock_prop,
        patch("telegram_bot.bot.ChatActionSender") as mock_cas,
    ):
        mock_cas.typing.return_value = _make_typing_cm()
        mock_prop.return_value.__enter__ = MagicMock()
        mock_prop.return_value.__exit__ = MagicMock()

        message = _make_voice_message()
        await bot.handle_voice(message)

    return mock_lf_client


class TestVoiceTraceMetadata:
    """Test that handle_voice writes same metadata keys as handle_query."""

    async def test_voice_trace_metadata_has_same_keys_as_text(self, mock_config):
        """handle_voice metadata should contain all keys from handle_query."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        voice_result = {
            **FULL_PIPELINE_RESULT,
            "stt_text": "тест запрос",
            "stt_duration_ms": 250.0,
            "voice_duration_s": 5.0,
            "input_type": "voice",
        }
        await _run_handle_voice(mock_config, voice_result, mock_lf)

        call_kwargs = mock_lf.update_current_trace.call_args.kwargs
        metadata = call_kwargs["metadata"]

        # All keys from handle_query must be present
        expected_keys = {
            "query_type",
            "cache_hit",
            "search_results_count",
            "rerank_applied",
            "llm_provider_model",
            "llm_ttft_ms",
            "response_style",
            "response_difficulty",
            "response_style_reasoning",
            "response_policy_mode",
            "answer_words",
            "answer_to_question_ratio",
            # Voice-specific
            "input_type",
            "stt_duration_ms",
            # Embedding resilience (#210)
            "embedding_error",
            "embedding_error_type",
        }
        assert expected_keys.issubset(set(metadata.keys()))

    async def test_trace_metadata_contains_memory_and_overhead(self, mock_config):
        """Trace metadata should include memory_messages_count and overhead proxy."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        result = {
            **FULL_PIPELINE_RESULT,
            "stt_text": "тест",
            "messages": [{"role": "user"}, {"role": "assistant"}],
            "checkpointer_overhead_proxy_ms": 39.0,
        }
        await _run_handle_voice(mock_config, result, mock_lf)

        metadata = mock_lf.update_current_trace.call_args.kwargs["metadata"]
        assert metadata["memory_messages_count"] == 2
        assert metadata["checkpointer_overhead_proxy_ms"] is not None


VOICE_PIPELINE_RESULT = {
    **FULL_PIPELINE_RESULT,
    "stt_text": "тест голосовой запрос",
    "stt_duration_ms": 250.0,
    "voice_duration_s": 5.0,
    "input_type": "voice",
}


class TestVoiceScores:
    """Test voice-specific Langfuse scores (#158)."""

    def test_voice_scores_written(self):
        """Voice result should emit stt_duration_ms and voice_duration_s scores."""
        mock_lf = MagicMock()
        _run_score_writer(VOICE_PIPELINE_RESULT, mock_lf)

        score_calls = mock_lf.create_score.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in score_calls}

        assert "stt_duration_ms" in score_map
        assert score_map["stt_duration_ms"]["value"] == 250.0
        assert "voice_duration_s" in score_map
        assert score_map["voice_duration_s"]["value"] == 5.0
        assert "input_type" in score_map
        assert score_map["input_type"]["value"] == "voice"
        assert score_map["input_type"]["data_type"] == "CATEGORICAL"

    def test_text_scores_omit_voice_metrics(self):
        """Text result should NOT emit stt_duration_ms or voice_duration_s scores."""
        mock_lf = MagicMock()
        _run_score_writer(FULL_PIPELINE_RESULT, mock_lf)

        score_names = [c.kwargs["name"] for c in mock_lf.create_score.call_args_list]

        assert "input_type" in score_names
        assert "stt_duration_ms" not in score_names
        assert "voice_duration_s" not in score_names


class TestMemoryScores:
    """Test conversation memory Langfuse scores (#159)."""

    @pytest.mark.parametrize(
        ("result_override", "expected_count"),
        [
            (
                {"messages": [{"role": "user"}, {"role": "assistant"}, {"role": "user"}]},
                3.0,
            ),
            (None, 0.0),  # None means pop "messages" key
        ],
        ids=["three_messages", "no_messages_key"],
    )
    def test_memory_messages_count(self, result_override, expected_count):
        """memory_messages_count tracks message count (0 when absent)."""
        mock_lf = MagicMock()
        if result_override is None:
            result = {**CHITCHAT_RESULT}
            result.pop("messages", None)
        else:
            result = {**FULL_PIPELINE_RESULT, **result_override}

        _run_score_writer(result, mock_lf)

        scores = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.create_score.call_args_list}
        assert scores["memory_messages_count"] == expected_count

    @pytest.mark.parametrize(
        ("has_summarize", "expected_value"),
        [(True, 1), (False, 0)],
        ids=["with_summarize_stage", "without_summarize_stage"],
    )
    def test_summarization_triggered(self, has_summarize, expected_value):
        """summarization_triggered reflects presence of summarize stage."""
        mock_lf = MagicMock()
        if has_summarize:
            result = {
                **FULL_PIPELINE_RESULT,
                "latency_stages": {
                    **FULL_PIPELINE_RESULT["latency_stages"],
                    "summarize": 0.250,
                },
            }
        else:
            result = CACHE_HIT_RESULT

        _run_score_writer(result, mock_lf)

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.create_score.call_args_list}
        assert scores["summarization_triggered"]["value"] == expected_value
        assert scores["summarization_triggered"]["data_type"] == "BOOLEAN"


def test_compute_checkpointer_overhead_proxy_ms():
    """Unit test for compute_checkpointer_overhead_proxy_ms helper."""
    result = {"latency_stages": {"classify": 0.001, "generate": 0.100}}
    # stages = 101ms, ainvoke wall = 140ms -> proxy overhead = 39ms
    assert compute_checkpointer_overhead_proxy_ms(result, 140.0) == pytest.approx(39.0, abs=0.1)
    # clamp at zero
    assert compute_checkpointer_overhead_proxy_ms(result, 50.0) == 0.0


class TestHistoryScores:
    """Test history-related Langfuse scores (#239, #310 supervisor path)."""

    @pytest.mark.parametrize(
        ("save_result", "expected_value"),
        [(True, 1), (False, 0)],
        ids=["save_success", "save_failure"],
    )
    async def test_history_save_success_score(self, mock_config, save_result, expected_value):
        """history_save_success reflects save_turn return value."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        history_svc = AsyncMock()
        history_svc.save_turn = AsyncMock(return_value=save_result)
        mock_lf, _bot = await _run_handle_query_supervisor(
            mock_config, mock_lf, history_service=history_svc
        )

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.create_score.call_args_list}
        assert scores["history_save_success"]["value"] == expected_value
        assert scores["history_save_success"]["data_type"] == "BOOLEAN"

    async def test_supervisor_model_score(self, mock_config):
        """supervisor_model CATEGORICAL score always written (#413)."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        history_svc = AsyncMock()
        history_svc.save_turn = AsyncMock(return_value=True)
        mock_lf, _ = await _run_handle_query_supervisor(
            mock_config, mock_lf, history_service=history_svc
        )

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.create_score.call_args_list}
        assert "supervisor_model" in scores
        assert scores["supervisor_model"]["value"] == "gpt-4o-mini"
        assert scores["supervisor_model"]["data_type"] == "CATEGORICAL"


class TestCheckpointerOverheadScore:
    """Test checkpointer_overhead_proxy_ms score (#159)."""

    def test_checkpointer_overhead_proxy_score_written(self):
        """checkpointer_overhead_proxy_ms written when present in result."""
        mock_lf = MagicMock()
        # Simulate rag_agent computing overhead: stages = 862ms, ainvoke = 901ms → 39ms
        result = {
            **FULL_PIPELINE_RESULT,
            "checkpointer_overhead_proxy_ms": compute_checkpointer_overhead_proxy_ms(
                FULL_PIPELINE_RESULT, 901.0
            ),
        }
        _run_score_writer(result, mock_lf)

        scores = {c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.create_score.call_args_list}
        assert scores["checkpointer_overhead_proxy_ms"] == pytest.approx(39.0, abs=0.1)


class TestScoreIsolation:
    """Verify scores use explicit trace_id via create_score, not session-wide (#435)."""

    def test_write_langfuse_scores_uses_create_score_with_trace_id(self):
        """All scores go through create_score(trace_id=...) for isolation (#435)."""
        mock_lf = MagicMock()
        _run_score_writer(FULL_PIPELINE_RESULT, mock_lf)

        # Verify create_score is used with explicit trace_id
        assert mock_lf.create_score.call_count > 0
        for call in mock_lf.create_score.call_args_list:
            assert call.kwargs["trace_id"] == _TEST_TRACE_ID
            # Idempotency key format: {trace_id}-{name}
            expected_id = f"{_TEST_TRACE_ID}-{call.kwargs['name']}"
            assert call.kwargs["score_id"] == expected_id

        # score_current_trace must NOT be used
        assert mock_lf.score_current_trace.call_count == 0

    async def test_supervisor_scores_use_create_score_with_trace_id(self, mock_config):
        """Supervisor-specific scores use create_score(trace_id=...) (#435)."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-xyz")

        await _run_handle_query_supervisor(mock_config, mock_lf)

        # All supervisor scores via create_score with trace_id
        score_names = [c.kwargs["name"] for c in mock_lf.create_score.call_args_list]
        assert "supervisor_model" in score_names
        assert "user_role" in score_names
        for call in mock_lf.create_score.call_args_list:
            assert call.kwargs["trace_id"] == "trace-xyz"
            assert "score_id" in call.kwargs  # idempotency key

        # score_current_trace must NOT be used
        assert mock_lf.score_current_trace.call_count == 0


class TestCreateScoreNoBarId:
    """Regression guard: create_score must use score_id=, never id= (#480)."""

    def test_no_bare_id_kwarg_in_create_score_calls(self):
        """All create_score() calls use score_id= for idempotency, not id=."""
        import ast
        from pathlib import Path

        targets = [
            Path("telegram_bot/scoring.py"),
            Path("telegram_bot/bot.py"),
            Path("telegram_bot/agents/history_graph/nodes.py"),
        ]
        violations = []
        for path in targets:
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
        assert not violations, f"create_score() uses bare id= (should be score_id=): {violations}"


class TestTextPathFeedbackButtons:
    """Test feedback buttons and source attribution in text path (#426)."""

    async def test_text_response_has_feedback_keyboard(self, mock_config):
        """Text response should include feedback inline keyboard."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        bot = _create_bot(mock_config)
        message = _make_message()

        # Mock agent that populates rag_result_store via side-channel
        def _agent_side_effect(state, config=None, **kw):
            cfg = config or kw.get("config", {})
            store = cfg.get("configurable", {}).get("rag_result_store")
            if isinstance(store, dict):
                store.update({"query_type": "FAQ", "documents": [], "response": "Answer"})
            return _mock_agent_result()

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(side_effect=_agent_side_effect)

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

        # Verify message.answer was called with reply_markup
        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("reply_markup") is not None

    async def test_text_response_has_markdown_parse_mode(self, mock_config):
        """Text response should use Markdown parse_mode."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        bot = _create_bot(mock_config)
        message = _make_message()

        def _agent_side_effect(state, config=None, **kw):
            cfg = config or kw.get("config", {})
            store = cfg.get("configurable", {}).get("rag_result_store")
            if isinstance(store, dict):
                store.update({"query_type": "FAQ", "documents": [], "response": "Answer"})
            return _mock_agent_result()

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(side_effect=_agent_side_effect)

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("parse_mode") == "Markdown"

    async def test_chitchat_response_no_feedback_keyboard(self, mock_config):
        """CHITCHAT response should NOT include feedback keyboard."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        bot = _create_bot(mock_config)
        message = _make_message()

        def _agent_side_effect(state, config=None, **kw):
            cfg = config or kw.get("config", {})
            store = cfg.get("configurable", {}).get("rag_result_store")
            if isinstance(store, dict):
                store.update({"query_type": "CHITCHAT", "documents": [], "response": "Привет!"})
            return _mock_agent_result(messages=[MagicMock(content="Привет!")])

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(side_effect=_agent_side_effect)

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("reply_markup") is None

    async def test_response_without_query_type_has_no_feedback_keyboard(self, mock_config):
        """Response without query_type in side-channel should NOT include feedback keyboard."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        bot = _create_bot(mock_config)
        message = _make_message()

        def _agent_side_effect(state, config=None, **kw):
            cfg = config or kw.get("config", {})
            store = cfg.get("configurable", {}).get("rag_result_store")
            if isinstance(store, dict):
                store.update({"documents": [], "response": "Answer"})
            return _mock_agent_result()

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(side_effect=_agent_side_effect)

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

        answer_calls = message.answer.call_args_list
        assert len(answer_calls) > 0
        last_call = answer_calls[-1]
        assert last_call.kwargs.get("reply_markup") is None


class TestTextPathSemanticCacheStore:
    """Test semantic cache persistence in SDK text path."""

    async def test_stores_semantic_cache_for_cacheable_query_type(self, mock_config):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        bot = _create_bot(mock_config)
        bot._cache = AsyncMock()
        bot._cache.store_semantic = AsyncMock()
        message = _make_message("какие документы нужны для покупки квартиры")

        def _agent_side_effect(state, config=None, **kw):
            cfg = config or kw.get("config", {})
            store = cfg.get("configurable", {}).get("rag_result_store")
            if isinstance(store, dict):
                store.update(
                    {
                        "query_type": "FAQ",
                        "query_embedding": [0.1, 0.2, 0.3],
                        "cache_hit": False,
                        "documents": [],
                    }
                )
            return _mock_agent_result(messages=[MagicMock(content="Ответ агентом")])

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(side_effect=_agent_side_effect)

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

        bot._cache.store_semantic.assert_called_once()
        kwargs = bot._cache.store_semantic.call_args.kwargs
        assert kwargs["query"] == message.text
        assert kwargs["response"] == "Ответ агентом"
        assert kwargs["query_type"] == "FAQ"
        assert "user_id" not in kwargs

    async def test_stores_semantic_cache_for_general_type(self, mock_config):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.create_score = MagicMock()
        mock_lf.get_current_trace_id = MagicMock(return_value="trace-abc-123")

        bot = _create_bot(mock_config)
        bot._cache = AsyncMock()
        bot._cache.store_semantic = AsyncMock()
        message = _make_message("расскажи в целом про рынок")

        def _agent_side_effect(state, config=None, **kw):
            cfg = config or kw.get("config", {})
            store = cfg.get("configurable", {}).get("rag_result_store")
            if isinstance(store, dict):
                store.update(
                    {
                        "query_type": "GENERAL",
                        "query_embedding": [0.1, 0.2, 0.3],
                        "cache_hit": False,
                        "documents": [],
                    }
                )
            return _mock_agent_result(messages=[MagicMock(content="Ответ агентом")])

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(side_effect=_agent_side_effect)

        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes"),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cas.typing.return_value = _make_typing_cm()
            await bot.handle_query(message)

        bot._cache.store_semantic.assert_called_once()
        kwargs = bot._cache.store_semantic.call_args.kwargs
        assert kwargs["query_type"] == "GENERAL"


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
