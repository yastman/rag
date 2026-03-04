"""Tests for PipelineEventStream — Redis Streams event log."""

from unittest.mock import AsyncMock

from langgraph.runtime import Runtime

from telegram_bot.integrations.event_stream import (
    STREAM_KEY,
    STREAM_MAXLEN,
    PipelineEventStream,
)


class TestPipelineEventStream:
    """Test PipelineEventStream.log_event."""

    async def test_log_event_calls_xadd(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(return_value="1234567890-0")
        stream = PipelineEventStream(redis_mock)

        result = await stream.log_event("pipeline_result", {"query": "test", "latency_ms": "42"})

        assert result == "1234567890-0"
        redis_mock.xadd.assert_awaited_once()

        call_args = redis_mock.xadd.call_args
        assert call_args[0][0] == STREAM_KEY
        fields = call_args[0][1]
        assert fields["event_type"] == "pipeline_result"
        assert fields["query"] == "test"
        assert fields["latency_ms"] == "42"
        assert "timestamp" in fields
        assert call_args[1]["maxlen"] == STREAM_MAXLEN
        assert call_args[1]["approximate"] is True

    async def test_log_event_no_data(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(return_value="1234567890-1")
        stream = PipelineEventStream(redis_mock)

        result = await stream.log_event("heartbeat")

        assert result == "1234567890-1"
        fields = redis_mock.xadd.call_args[0][1]
        assert fields["event_type"] == "heartbeat"
        assert "timestamp" in fields
        assert len(fields) == 2

    async def test_returns_none_when_no_redis(self):
        stream = PipelineEventStream(None)

        result = await stream.log_event("test_event", {"key": "value"})

        assert result is None

    async def test_returns_none_on_redis_error(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(side_effect=ConnectionError("Redis down"))
        stream = PipelineEventStream(redis_mock)

        result = await stream.log_event("test_event", {"key": "value"})

        assert result is None

    async def test_coerces_values_to_str(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(return_value="1234567890-2")
        stream = PipelineEventStream(redis_mock)

        await stream.log_event("test", {"count": 42, "flag": True, "rate": 0.95})

        fields = redis_mock.xadd.call_args[0][1]
        assert fields["count"] == "42"
        assert fields["flag"] == "True"
        assert fields["rate"] == "0.95"


class TestCacheStoreNodeEventStream:
    """Test event_stream integration in cache_store_node."""

    async def test_cache_store_logs_event(self):
        from telegram_bot.graph.nodes.cache import cache_store_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = "generated answer"
        state["search_results_count"] = 5
        state["rerank_applied"] = True
        state["latency_stages"] = {"cache_check": 0.01, "generate": 0.5}

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        event_stream = AsyncMock()
        event_stream.log_event = AsyncMock(return_value="entry-id")

        await cache_store_node(
            state, Runtime(context={"cache": cache, "event_stream": event_stream})
        )

        event_stream.log_event.assert_awaited_once()
        call_args = event_stream.log_event.call_args
        assert call_args[0][0] == "pipeline_result"
        data = call_args[0][1]
        assert data["query"] == "test query"
        assert data["query_type"] == "GENERAL"
        assert data["search_count"] == 5
        assert data["rerank_applied"] is True
        assert data["cache_hit"] is False
        assert data["latency_ms"] == 510

    async def test_cache_store_works_without_event_stream(self):
        from telegram_bot.graph.nodes.cache import cache_store_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"  # Must be cacheable type (FAQ/ENTITY/STRUCTURED)
        state["query_embedding"] = [0.1] * 1024
        state["response"] = "answer"

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        result = await cache_store_node(state, Runtime(context={"cache": cache}))

        assert result["response"] == "answer"
        cache.store_semantic.assert_awaited_once()

    async def test_cache_store_no_event_when_no_response(self):
        from telegram_bot.graph.nodes.cache import cache_store_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = ""

        cache = AsyncMock()
        event_stream = AsyncMock()

        await cache_store_node(
            state, Runtime(context={"cache": cache, "event_stream": event_stream})
        )

        event_stream.log_event.assert_not_awaited()

    async def test_cache_store_ignores_non_numeric_latency_values(self):
        from telegram_bot.graph.nodes.cache import cache_store_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = "generated answer"
        state["latency_stages"] = {
            "cache_check": 0.01,
            "rewrite": 0.20,
            "rewrite_provider_model": "gpt-4o-mini",
        }

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()
        event_stream = AsyncMock()
        event_stream.log_event = AsyncMock(return_value="entry-id")

        await cache_store_node(
            state, Runtime(context={"cache": cache, "event_stream": event_stream})
        )

        event_stream.log_event.assert_awaited_once()
        data = event_stream.log_event.call_args[0][1]
        assert data["latency_ms"] == 210
