"""Tests for _handle_query_supervisor phases (content filter, semantic cache)
and handle_query handoff mode routing.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.config import BotConfig


def _make_config(**overrides) -> BotConfig:
    defaults = {
        "telegram_token": "test-token",
        "llm_api_key": "llm-key",
        "llm_base_url": "https://api.example.com/v1",
        "llm_model": "gpt-4o-mini",
        "qdrant_url": "http://localhost:6333",
        "redis_url": "redis://localhost:6379",
        "rerank_provider": "none",
        "content_filter_enabled": True,
        "guard_mode": "hard",
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


def _make_message(text="test query"):
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=12345)
    message.chat = MagicMock(id=12345)
    message.message_id = 100
    message.message_thread_id = None
    message.bot = MagicMock(send_chat_action=AsyncMock())
    message.answer = AsyncMock()
    return message


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

        from src.runtime.graph.nodes.guard import _BLOCKED_RESPONSE

        with (
            patch("telegram_bot.bot.classify_query", return_value="FAQ"),
            patch(
                "telegram_bot.bot.detect_injection",
                return_value=(True, 0.9, "sql_injection"),
            ),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.score"),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_lf.get_current_trace_id.return_value = "trace123"
            mock_get_client.return_value = mock_lf

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

        from src.runtime.graph.nodes.guard import _BLOCKED_RESPONSE

        with (
            patch("telegram_bot.bot.classify_query", return_value="CHITCHAT"),
            patch(
                "telegram_bot.bot.detect_injection",
                return_value=(True, 0.7, "prompt_injection"),
            ),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.score"),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch(
                "telegram_bot.bot._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_lf.get_current_trace_id.return_value = "trace456"
            mock_lf.start_as_current_observation.return_value.__enter__ = MagicMock()
            mock_lf.start_as_current_observation.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_get_client.return_value = mock_lf

            bot._resolve_user_role = AsyncMock(return_value="client")

            # Mock the agent to return a simple response
            mock_agent = AsyncMock()
            mock_agent.ainvoke = AsyncMock(
                return_value={"messages": [MagicMock(content="agent response")]}
            )
            mock_agent_factory.return_value = mock_agent

            # Mock _send_markdown_chunks to avoid complex downstream
            bot._send_markdown_chunks = AsyncMock()
            # Mock _spawn_history_save
            bot._spawn_history_save = MagicMock(return_value=None)

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        # Should NOT have sent the blocked response
        for call in message.answer.call_args_list:
            assert call.args[0] != _BLOCKED_RESPONSE
        # Method should have returned some response (not blocked)
        assert result != _BLOCKED_RESPONSE

    async def test_content_filter_disabled_skips_guard(self):
        """When content_filter_enabled=False, detect_injection is never called."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("DROP TABLE users;")

        with (
            patch("telegram_bot.bot.classify_query", return_value="CHITCHAT"),
            patch("telegram_bot.bot.detect_injection") as mock_detect,
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.score"),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch(
                "telegram_bot.bot._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_lf.get_current_trace_id.return_value = "trace789"
            mock_lf.start_as_current_observation.return_value.__enter__ = MagicMock()
            mock_lf.start_as_current_observation.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_get_client.return_value = mock_lf

            bot._resolve_user_role = AsyncMock(return_value="client")

            mock_agent = AsyncMock()
            mock_agent.ainvoke = AsyncMock(
                return_value={"messages": [MagicMock(content="agent response")]}
            )
            mock_agent_factory.return_value = mock_agent

            bot._send_markdown_chunks = AsyncMock()
            bot._spawn_history_save = MagicMock(return_value=None)

            await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        mock_detect.assert_not_called()


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

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
        ):
            mock_lf = MagicMock()
            mock_get_client.return_value = mock_lf

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

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch.object(bot, "_handle_query_supervisor", new_callable=AsyncMock) as mock_hqs,
        ):
            mock_lf = MagicMock()
            mock_lf.update_current_span = MagicMock()
            mock_get_client.return_value = mock_lf
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
        # AND _handle_query_supervisor was called (continues processing)
        mock_hqs.assert_awaited_once()

    async def test_no_handoff_proceeds_normally(self):
        """No handoff state proceeds directly to _handle_query_supervisor."""
        bot = _create_bot()
        message = _make_message("hello")
        bot._handoff_state = None

        with (
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch.object(bot, "_handle_query_supervisor", new_callable=AsyncMock) as mock_hqs,
        ):
            mock_lf = MagicMock()
            mock_lf.update_current_span = MagicMock()
            mock_get_client.return_value = mock_lf
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
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.score"),
            patch(
                "telegram_bot.bot._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_lf.get_current_trace_id.return_value = "trace_cache_hit"
            mock_lf.start_as_current_observation.return_value.__enter__ = MagicMock()
            mock_lf.start_as_current_observation.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_get_client.return_value = mock_lf

            bot._resolve_user_role = AsyncMock(return_value="client")

            # Setup cache to return a hit
            bot._cache.check_semantic = AsyncMock(return_value="Cached: deposit is 10%")

            # Mock helper functions that cache-hit path calls
            bot._send_markdown_chunks = AsyncMock()

            # Mock pre-agent helper functions needed before cache check
            with (
                patch(
                    "telegram_bot.bot.get_query_topic_hint",
                    return_value=None,
                ),
                patch(
                    "telegram_bot.bot.get_grounding_mode",
                    return_value="default",
                ),
                patch(
                    "telegram_bot.bot.detect_filter_sensitive_query",
                ) as mock_filter_signal,
                patch(
                    "telegram_bot.bot.is_contextual_query",
                    return_value=False,
                ),
                patch(
                    "telegram_bot.bot.resolve_semantic_cache_signature",
                    return_value=None,
                ),
            ):
                mock_filter_signal.return_value = MagicMock(is_filter_sensitive=False, reasons=[])

                result = await bot._handle_query_supervisor(
                    message, time.perf_counter(), locale="ru", root_trace_metadata={}
                )

        # Should return cached response
        assert result == "Cached: deposit is 10%"
        # Agent should NOT be created
        mock_agent_factory.assert_not_called()
        # Should have sent the cached response via _send_markdown_chunks
        bot._send_markdown_chunks.assert_awaited_once()

    async def test_cache_miss_proceeds_to_agent(self):
        """Cache MISS proceeds to agent invocation."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("What are the nearby schools?")

        with (
            patch("telegram_bot.bot.classify_query", return_value="FAQ"),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.score"),
            patch(
                "telegram_bot.bot._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_lf.get_current_trace_id.return_value = "trace_cache_miss"
            mock_lf.start_as_current_observation.return_value.__enter__ = MagicMock()
            mock_lf.start_as_current_observation.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_get_client.return_value = mock_lf

            bot._resolve_user_role = AsyncMock(return_value="client")

            # Cache returns None (miss)
            bot._cache.check_semantic = AsyncMock(return_value=None)

            # Mock the agent
            mock_agent = AsyncMock()
            mock_agent.ainvoke = AsyncMock(
                return_value={"messages": [MagicMock(content="agent says schools nearby")]}
            )
            mock_agent_factory.return_value = mock_agent

            bot._send_markdown_chunks = AsyncMock()
            bot._spawn_history_save = MagicMock(return_value=None)

            with (
                patch(
                    "telegram_bot.bot.get_query_topic_hint",
                    return_value=None,
                ),
                patch(
                    "telegram_bot.bot.get_grounding_mode",
                    return_value="default",
                ),
                patch(
                    "telegram_bot.bot.detect_filter_sensitive_query",
                ) as mock_filter_signal,
                patch(
                    "telegram_bot.bot.is_contextual_query",
                    return_value=False,
                ),
                patch(
                    "telegram_bot.bot.resolve_semantic_cache_signature",
                    return_value=None,
                ),
            ):
                mock_filter_signal.return_value = MagicMock(is_filter_sensitive=False, reasons=[])

                result = await bot._handle_query_supervisor(
                    message, time.perf_counter(), locale="ru", root_trace_metadata={}
                )

        # Agent was invoked
        mock_agent_factory.assert_called_once()
        # Result came from agent
        assert "agent says schools nearby" in result

    async def test_non_cacheable_query_type_skips_cache(self):
        """CHITCHAT query type (in _NO_RAG_QUERY_TYPES) skips semantic cache entirely."""
        config = _make_config(content_filter_enabled=False)
        bot = _create_bot(config)
        message = _make_message("how are you?")

        with (
            patch("telegram_bot.bot.classify_query", return_value="CHITCHAT"),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.get_client") as mock_get_client,
            patch("telegram_bot.bot.write_langfuse_scores"),
            patch("telegram_bot.bot.score"),
            patch(
                "telegram_bot.bot._get_or_compute_pre_agent_dense",
                new_callable=AsyncMock,
                return_value=[0.1] * 768,
            ),
            patch("telegram_bot.bot.create_bot_agent") as mock_agent_factory,
            patch("telegram_bot.bot.create_callback_handler", return_value=None),
        ):
            mock_prop.return_value.__enter__ = MagicMock(return_value=None)
            mock_prop.return_value.__exit__ = MagicMock(return_value=False)
            mock_lf = MagicMock()
            mock_lf.get_current_trace_id.return_value = "trace_chitchat"
            mock_get_client.return_value = mock_lf

            bot._resolve_user_role = AsyncMock(return_value="client")

            # Mock the agent
            mock_agent = AsyncMock()
            mock_agent.ainvoke = AsyncMock(
                return_value={"messages": [MagicMock(content="I am doing well!")]}
            )
            mock_agent_factory.return_value = mock_agent

            bot._send_markdown_chunks = AsyncMock()
            bot._spawn_history_save = MagicMock(return_value=None)

            result = await bot._handle_query_supervisor(
                message, time.perf_counter(), locale="ru", root_trace_metadata={}
            )

        # Cache check_semantic should NOT be called (CHITCHAT not in CACHEABLE_QUERY_TYPES)
        bot._cache.check_semantic.assert_not_called()
        # Agent was invoked directly
        mock_agent_factory.assert_called_once()
        assert "I am doing well!" in result
