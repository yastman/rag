# tests/unit/test_bot_scores.py
"""Tests for Langfuse score writing in handle_query."""

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
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
    """Create PropertyBot with all deps mocked."""
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3Embeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
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


async def _run_handle_query(mock_config, graph_result, mock_lf_client, *, history_service=None):
    """Shared helper: run handle_query with mocked graph and Langfuse client.

    Args:
        history_service: If provided, set bot._history_service before invoking.
    """
    bot = _create_bot(mock_config)
    if history_service is not None:
        bot._history_service = history_service

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

        await bot.handle_query(_make_message())

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
    """Test that Langfuse scores are written after graph.ainvoke."""

    async def test_scores_written_full_pipeline(self, mock_config):
        """All scores should be written after a full pipeline run."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await _run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        # Extract all score names from calls
        score_calls = mock_lf.score_current_trace.call_args_list
        score_names = [call.kwargs["name"] for call in score_calls]

        expected_names = [
            # Original 14
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
            # Latency breakdown (#147): streaming path
            "streaming_enabled",
            "llm_timeout",
            "llm_stream_recovery",
            "llm_decode_ms",
            "llm_tps",
            "llm_queue_unavailable",
            # Response length control (#129)
            "answer_words",
            "answer_chars",
            "answer_to_question_ratio",
            "response_style_applied",
            # Voice transcription (#151)
            "input_type",
            # Embedding resilience (#210)
            "bge_embed_error",
            "bge_embed_latency_ms",
            # Source attribution (#225)
            "sources_shown",
            "sources_count",
            # Conversation memory (#159)
            "memory_messages_count",
            "summarization_triggered",
            "checkpointer_overhead_proxy_ms",
        ]
        assert sorted(score_names) == sorted(expected_names)
        assert mock_lf.score_current_trace.call_count == 32

    async def test_score_values_full_pipeline(self, mock_config):
        """Score values should match the graph result state."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await _run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
        }
        # query_type: STRUCTURED → 2
        assert scores["query_type"] == 2.0
        # cache miss
        assert scores["semantic_cache_hit"] == 0.0
        # rerank applied
        assert scores["rerank_applied"] == 1.0
        # 5 results
        assert scores["results_count"] == 5.0
        # not empty
        assert scores["no_results"] == 0.0
        # generate in latency_stages → LLM used
        assert scores["llm_used"] == 1.0
        # latency_total_ms = pipeline_wall_ms (wall-time, not sum of stages)
        assert abs(scores["latency_total_ms"] - FULL_PIPELINE_RESULT["pipeline_wall_ms"]) < 0.01
        # embeddings/search cache misses, confidence from grade
        assert scores["embeddings_cache_hit"] == 0.0
        assert scores["search_cache_hit"] == 0.0
        assert scores["confidence_score"] == 0.85
        assert scores["answer_words"] == 12.0
        assert scores["answer_chars"] == 65.0
        assert scores["answer_to_question_ratio"] == 2.4
        assert scores["response_style_applied"] == 1.0  # balanced

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
    async def test_score_values_by_result_type(self, mock_config, result_fixture, expected_scores):
        """Score values should match per result type (cache hit, chitchat)."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result_data = {"CACHE_HIT_RESULT": CACHE_HIT_RESULT, "CHITCHAT_RESULT": CHITCHAT_RESULT}[
            result_fixture
        ]
        await _run_handle_query(mock_config, result_data, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
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
    async def test_style_applied_not_emitted(self, mock_config, result_override, test_id):
        """response_style_applied must NOT be emitted in shadow/legacy paths."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        base = FULL_PIPELINE_RESULT if "shadow" in test_id else CACHE_HIT_RESULT
        result = {**base, **result_override}
        await _run_handle_query(mock_config, result, mock_lf)

        score_names = [c.kwargs["name"] for c in mock_lf.score_current_trace.call_args_list]
        assert "response_style_applied" not in score_names

    async def test_scores_written_even_on_null_client(self, mock_config):
        """When Langfuse disabled, _NullLangfuseClient.score_current_trace is called (no-op)."""
        from telegram_bot.observability import _NullLangfuseClient

        mock_lf = _NullLangfuseClient()
        # Should not raise — NullClient silently ignores
        await _run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)


class TestLatencyBreakdownScores:
    """Test latency breakdown score writing (#147)."""

    async def test_streaming_path_writes_numeric_and_boolean_scores(self, mock_config):
        """Streaming: writes llm_decode_ms, llm_tps as NUMERIC; boolean flags."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await _run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        # NUMERIC scores written
        assert score_map["llm_decode_ms"]["value"] == 300.0
        assert score_map["llm_tps"]["value"] == 42.5

        # BOOLEAN flags
        assert score_map["streaming_enabled"]["value"] == 1
        assert score_map["streaming_enabled"]["data_type"] == "BOOLEAN"
        assert score_map["llm_timeout"]["value"] == 0
        assert score_map["llm_timeout"]["data_type"] == "BOOLEAN"
        assert score_map["llm_stream_recovery"]["value"] == 0
        assert score_map["llm_stream_recovery"]["data_type"] == "BOOLEAN"

        # queue_unavailable because queue_ms is None
        assert score_map["llm_queue_unavailable"]["value"] == 1
        assert score_map["llm_queue_unavailable"]["data_type"] == "BOOLEAN"
        # No llm_decode_unavailable (decode_ms was written)
        assert "llm_decode_unavailable" not in score_map

    async def test_non_streaming_writes_unavailable_flags(self, mock_config):
        """Non-streaming: writes *_unavailable BOOLEAN flags, skips NUMERIC decode/tps."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await _run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        # NUMERIC scores NOT written
        assert "llm_decode_ms" not in score_map
        assert "llm_tps" not in score_map
        assert "llm_queue_ms" not in score_map

        # Unavailable flags written
        assert score_map["llm_decode_unavailable"]["value"] == 1
        assert score_map["llm_decode_unavailable"]["data_type"] == "BOOLEAN"
        assert score_map["llm_tps_unavailable"]["value"] == 1
        assert score_map["llm_queue_unavailable"]["value"] == 1

        # streaming_enabled = False
        assert score_map["streaming_enabled"]["value"] == 0
        assert score_map["streaming_enabled"]["data_type"] == "BOOLEAN"

    async def test_hard_fail_writes_timeout_true(self, mock_config):
        """Hard LLM failure: llm_timeout=1 BOOLEAN."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        timeout_result = {
            **CHITCHAT_RESULT,
            "llm_timeout": True,
            "llm_stream_recovery": False,
            "streaming_enabled": False,
            "llm_decode_ms": None,
            "llm_tps": None,
            "llm_queue_ms": None,
        }

        await _run_handle_query(mock_config, timeout_result, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
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
        mock_lf.score_current_trace = MagicMock()

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
        mock_lf.score_current_trace = MagicMock()

        result = {
            **FULL_PIPELINE_RESULT,
            "messages": [{"role": "user"}, {"role": "assistant"}],
            "checkpointer_overhead_proxy_ms": 39.0,
        }
        await _run_handle_query(mock_config, result, mock_lf)

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

    async def test_voice_scores_written(self, mock_config):
        """Voice result should emit stt_duration_ms and voice_duration_s scores."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await _run_handle_query(mock_config, VOICE_PIPELINE_RESULT, mock_lf)

        score_calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in score_calls}

        # Voice-specific scores must be present
        assert "stt_duration_ms" in score_map
        assert score_map["stt_duration_ms"]["value"] == 250.0

        assert "voice_duration_s" in score_map
        assert score_map["voice_duration_s"]["value"] == 5.0

        assert "input_type" in score_map
        assert score_map["input_type"]["value"] == "voice"
        assert score_map["input_type"]["data_type"] == "CATEGORICAL"

    async def test_text_scores_omit_voice_metrics(self, mock_config):
        """Text result should NOT emit stt_duration_ms or voice_duration_s scores."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await _run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        score_names = [c.kwargs["name"] for c in mock_lf.score_current_trace.call_args_list]

        # input_type always written (as "text")
        assert "input_type" in score_names
        # Voice-only scores NOT written for text input
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
    async def test_memory_messages_count(self, mock_config, result_override, expected_count):
        """memory_messages_count tracks message count (0 when absent)."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        if result_override is None:
            result = {**CHITCHAT_RESULT}
            result.pop("messages", None)
        else:
            result = {**FULL_PIPELINE_RESULT, **result_override}

        await _run_handle_query(mock_config, result, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["memory_messages_count"] == expected_count

    @pytest.mark.parametrize(
        ("has_summarize", "expected_value"),
        [(True, 1), (False, 0)],
        ids=["with_summarize_stage", "without_summarize_stage"],
    )
    async def test_summarization_triggered(self, mock_config, has_summarize, expected_value):
        """summarization_triggered reflects presence of summarize stage."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

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

        await _run_handle_query(mock_config, result, mock_lf)

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list}
        assert scores["summarization_triggered"]["value"] == expected_value
        assert scores["summarization_triggered"]["data_type"] == "BOOLEAN"


def test_compute_checkpointer_overhead_proxy_ms():
    """Unit test for _compute_checkpointer_overhead_proxy_ms helper."""
    from telegram_bot.bot import _compute_checkpointer_overhead_proxy_ms

    result = {"latency_stages": {"classify": 0.001, "generate": 0.100}}
    # stages = 101ms, ainvoke wall = 140ms -> proxy overhead = 39ms
    assert _compute_checkpointer_overhead_proxy_ms(result, 140.0) == pytest.approx(39.0, abs=0.1)
    # clamp at zero
    assert _compute_checkpointer_overhead_proxy_ms(result, 50.0) == 0.0


class TestHistoryScores:
    """Test history-related Langfuse scores (#239)."""

    @pytest.mark.parametrize(
        ("save_result", "expected_value"),
        [(True, 1), (False, 0)],
        ids=["save_success", "save_failure"],
    )
    async def test_history_save_success_score(self, mock_config, save_result, expected_value):
        """history_save_success reflects save_turn return value."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        history_svc = AsyncMock()
        history_svc.save_turn = AsyncMock(return_value=save_result)
        mock_lf, _bot = await _run_handle_query(
            mock_config, FULL_PIPELINE_RESULT, mock_lf, history_service=history_svc
        )

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list}
        assert scores["history_save_success"]["value"] == expected_value
        assert scores["history_save_success"]["data_type"] == "BOOLEAN"

    async def test_history_backend_score(self, mock_config):
        """history_backend=qdrant CATEGORICAL score when service available."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        history_svc = AsyncMock()
        history_svc.save_turn = AsyncMock(return_value=True)
        mock_lf, _ = await _run_handle_query(
            mock_config, FULL_PIPELINE_RESULT, mock_lf, history_service=history_svc
        )

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list}
        assert "history_backend" in scores
        assert scores["history_backend"]["value"] == "qdrant"
        assert scores["history_backend"]["data_type"] == "CATEGORICAL"


class TestCheckpointerOverheadScore:
    """Test checkpointer_overhead_proxy_ms score (#159)."""

    async def test_checkpointer_overhead_proxy_score_written(self, mock_config):
        """checkpointer_overhead_proxy_ms computed from ainvoke wall-time minus stages."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        # FULL_PIPELINE_RESULT stages sum to 862ms (0.862s)
        # Simulate ainvoke taking 0.901s (901ms) → overhead proxy = 39ms
        perf_values = iter(
            [
                0.0,  # pipeline_start
                1.0,  # invoke_start
                1.901,  # after ainvoke → ainvoke_wall_ms = 901ms
                2.0,  # pipeline_wall_ms
            ]
        )
        with patch("telegram_bot.bot.time.perf_counter", side_effect=perf_values):
            await _run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["checkpointer_overhead_proxy_ms"] == pytest.approx(39.0, abs=0.1)
