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

    async def _run_handle_query(self, mock_config, graph_result, mock_lf_client):
        """Helper: run handle_query with mocked graph and Langfuse client."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            # propagate_attributes is a context manager
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_scores_written_full_pipeline(self, mock_config):
        """All scores should be written after a full pipeline run."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

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
            # Conversation memory (#159)
            "memory_messages_count",
            "summarization_triggered",
        ]
        assert sorted(score_names) == sorted(expected_names)
        assert mock_lf.score_current_trace.call_count == 27

    @pytest.mark.asyncio
    async def test_score_values_full_pipeline(self, mock_config):
        """Score values should match the graph result state."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

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

    @pytest.mark.asyncio
    async def test_score_values_cache_hit(self, mock_config):
        """Cache hit should set semantic_cache_hit=1.0, llm_used=0.0."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
        }
        assert scores["semantic_cache_hit"] == 1.0
        assert scores["llm_used"] == 0.0
        assert scores["rerank_applied"] == 0.0
        assert scores["results_count"] == 0.0

    @pytest.mark.asyncio
    async def test_score_values_chitchat(self, mock_config):
        """Chitchat should set query_type=0, no LLM, no results."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CHITCHAT_RESULT, mock_lf)

        scores = {
            call.kwargs["name"]: call.kwargs["value"]
            for call in mock_lf.score_current_trace.call_args_list
        }
        # CHITCHAT → 0
        assert scores["query_type"] == 0.0
        assert scores["llm_used"] == 0.0
        assert scores["results_count"] == 0.0
        assert scores["no_results"] == 1.0

    @pytest.mark.asyncio
    async def test_shadow_mode_does_not_emit_style_applied(self, mock_config):
        """Shadow policy mode must not emit response_style_applied metric."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        shadow_result = {
            **FULL_PIPELINE_RESULT,
            "response_policy_mode": "shadow",
            "response_style": "short",
        }
        await self._run_handle_query(mock_config, shadow_result, mock_lf)

        score_names = [c.kwargs["name"] for c in mock_lf.score_current_trace.call_args_list]
        assert "response_style_applied" not in score_names
        assert "answer_to_question_ratio" in score_names

    @pytest.mark.asyncio
    async def test_empty_style_without_policy_mode_does_not_emit_style_applied(self, mock_config):
        """Legacy/cache paths may include empty response_style without enforced policy."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        legacy_result = {
            **CACHE_HIT_RESULT,
            "response_style": "",
            # response_policy_mode intentionally missing
        }
        await self._run_handle_query(mock_config, legacy_result, mock_lf)

        score_names = [c.kwargs["name"] for c in mock_lf.score_current_trace.call_args_list]
        assert "response_style_applied" not in score_names

    @pytest.mark.asyncio
    async def test_scores_written_even_on_null_client(self, mock_config):
        """When Langfuse disabled, _NullLangfuseClient.score_current_trace is called (no-op)."""
        from telegram_bot.observability import _NullLangfuseClient

        mock_lf = _NullLangfuseClient()

        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=FULL_PIPELINE_RESULT)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            # Should not raise — NullClient silently ignores
            await bot.handle_query(_make_message())


class TestLatencyBreakdownScores:
    """Test latency breakdown score writing (#147)."""

    async def _run_handle_query(self, mock_config, graph_result, mock_lf_client):
        """Helper: run handle_query with mocked graph and Langfuse client."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_streaming_path_writes_numeric_and_boolean_scores(self, mock_config):
        """Streaming: writes llm_decode_ms, llm_tps as NUMERIC; boolean flags."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

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

    @pytest.mark.asyncio
    async def test_non_streaming_writes_unavailable_flags(self, mock_config):
        """Non-streaming: writes *_unavailable BOOLEAN flags, skips NUMERIC decode/tps."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

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

    @pytest.mark.asyncio
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

        await self._run_handle_query(mock_config, timeout_result, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        assert score_map["llm_timeout"]["value"] == 1
        assert score_map["llm_timeout"]["data_type"] == "BOOLEAN"


class TestVoiceTraceMetadata:
    """Test that handle_voice writes same metadata keys as handle_query."""

    async def _run_handle_voice(self, mock_config, graph_result, mock_lf_client):
        """Helper: run handle_voice with mocked graph and Langfuse client."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            message = _make_voice_message()
            await bot.handle_voice(message)

        return mock_lf_client

    @pytest.mark.asyncio
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
        await self._run_handle_voice(mock_config, voice_result, mock_lf)

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
        }
        assert expected_keys.issubset(set(metadata.keys()))


VOICE_PIPELINE_RESULT = {
    **FULL_PIPELINE_RESULT,
    "stt_text": "тест голосовой запрос",
    "stt_duration_ms": 250.0,
    "voice_duration_s": 5.0,
    "input_type": "voice",
}


class TestVoiceScores:
    """Test voice-specific Langfuse scores (#158)."""

    @pytest.mark.asyncio
    async def test_voice_scores_written(self, mock_config):
        """Voice result should emit stt_duration_ms and voice_duration_s scores."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=VOICE_PIPELINE_RESULT)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

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

    @pytest.mark.asyncio
    async def test_text_scores_omit_voice_metrics(self, mock_config):
        """Text result should NOT emit stt_duration_ms or voice_duration_s scores."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=FULL_PIPELINE_RESULT)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        score_names = [c.kwargs["name"] for c in mock_lf.score_current_trace.call_args_list]

        # input_type always written (as "text")
        assert "input_type" in score_names
        # Voice-only scores NOT written for text input
        assert "stt_duration_ms" not in score_names
        assert "voice_duration_s" not in score_names


class TestMemoryScores:
    """Test conversation memory Langfuse scores (#159)."""

    async def _run_handle_query(self, mock_config, graph_result, mock_lf_client):
        """Helper: same as TestScoreWriting._run_handle_query."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_memory_messages_count_written(self, mock_config):
        """memory_messages_count = len(result['messages'])."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {
            **FULL_PIPELINE_RESULT,
            "messages": [{"role": "user"}, {"role": "assistant"}, {"role": "user"}],
        }
        await self._run_handle_query(mock_config, result, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["memory_messages_count"] == 3.0

    @pytest.mark.asyncio
    async def test_summarization_triggered_true(self, mock_config):
        """summarization_triggered=1 when summarize_ms > 0."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {
            **FULL_PIPELINE_RESULT,
            "latency_stages": {**FULL_PIPELINE_RESULT["latency_stages"], "summarize": 0.250},
        }
        await self._run_handle_query(mock_config, result, mock_lf)

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list}
        assert scores["summarization_triggered"]["value"] == 1
        assert scores["summarization_triggered"]["data_type"] == "BOOLEAN"
        assert scores["summarize_ms"]["value"] == pytest.approx(250.0, abs=1)

    @pytest.mark.asyncio
    async def test_summarization_triggered_false(self, mock_config):
        """summarization_triggered=0 when no summarize stage."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

        scores = {c.kwargs["name"]: c.kwargs for c in mock_lf.score_current_trace.call_args_list}
        assert scores["summarization_triggered"]["value"] == 0
        assert scores["summarization_triggered"]["data_type"] == "BOOLEAN"

    @pytest.mark.asyncio
    async def test_memory_messages_count_zero_when_no_messages(self, mock_config):
        """memory_messages_count=0 when messages key absent."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        result = {**CHITCHAT_RESULT}
        result.pop("messages", None)  # no messages key

        await self._run_handle_query(mock_config, result, mock_lf)

        scores = {
            c.kwargs["name"]: c.kwargs["value"] for c in mock_lf.score_current_trace.call_args_list
        }
        assert scores["memory_messages_count"] == 0.0
