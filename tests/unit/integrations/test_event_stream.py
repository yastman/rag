"""Tests for PipelineEventStream — Redis Streams event log."""

from unittest.mock import AsyncMock

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
