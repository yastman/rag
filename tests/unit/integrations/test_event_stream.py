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
        redis_mock.xadd = AsyncMock(return_value="12345-0")
        stream = PipelineEventStream(redis_mock)
        data = {"query": "test", "response": "answer"}
        entry_id = await stream.log_event("pipeline_result", data)
        assert entry_id == "12345-0"
        redis_mock.xadd.assert_awaited_once()
        call_args = redis_mock.xadd.call_args
        assert call_args[0][0] == STREAM_KEY
        fields = call_args[0][1]
        assert fields.pop("event_type") == "pipeline_result"
        assert fields.pop("query") == "test"
        assert fields.pop("response") == "answer"
        assert "timestamp" in fields
        assert call_args[1]["maxlen"] == STREAM_MAXLEN
        assert call_args[1]["approximate"] is True

    async def test_log_event_no_data(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(return_value="12345-0")
        stream = PipelineEventStream(redis_mock)
        entry_id = await stream.log_event("test_event")
        assert entry_id == "12345-0"
        call_args = redis_mock.xadd.call_args
        fields = call_args[0][1]
        assert fields["event_type"] == "test_event"
        assert "timestamp" in fields
        assert len(fields) == 2

    async def test_returns_none_when_no_redis(self):
        stream = PipelineEventStream(None)
        result = await stream.log_event("pipeline_result", {"query": "test"})
        assert result is None

    async def test_returns_none_on_redis_error(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(side_effect=ConnectionError("Redis down"))
        stream = PipelineEventStream(redis_mock)
        result = await stream.log_event("pipeline_result", {"query": "test"})
        assert result is None

    async def test_coerces_values_to_str(self):
        redis_mock = AsyncMock()
        redis_mock.xadd = AsyncMock(return_value="12345-0")
        stream = PipelineEventStream(redis_mock)
        data = {"count": 42, "flag": True, "rate": 0.95}
        await stream.log_event("test", data)
        fields = redis_mock.xadd.call_args[0][1]
        assert fields["count"] == "42"
        assert fields["flag"] == "True"
        assert fields["rate"] == "0.95"
