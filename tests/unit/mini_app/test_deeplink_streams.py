# tests/unit/mini_app/test_deeplink_streams.py
"""Producer-side contract for the Mini App deep-link Redis Streams migration.

Issue #1239 replaces the volatile ``redis.publish('miniapp:start', ...)``
fire-and-forget call in ``mini_app.api.start_expert`` with a Redis Streams
``XADD`` so the bot subscriber can ack messages and replay anything it
missed across restarts.

This module pins three properties on the producer:

1. ``XADD`` is called against the canonical stream key
   ``miniapp:start:stream`` with the deep-link payload as fields.
2. The legacy ``PUBLISH`` call is removed (no longer issued for the
   ``miniapp:start`` channel).
3. The stream is bounded with ``maxlen`` + ``approximate=True`` so a
   stuck consumer cannot grow it without limit.

The companion consumer-side tests live in ``tests/unit/test_bot_deeplink.py``
(``TestSubscriberStreamsContract``).

Refs #1239. Context7 source for the redis-py Streams API used:
``/redis/redis-py`` docs/commands.md#xadd, docs/examples/redis-stream-example.ipynb.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, get_redis, get_validated_init_data


def _stub_init_data() -> dict:
    return {"user": {"id": 123, "first_name": "Test"}, "auth_date": "0"}


def _override_redis(mock_redis: AsyncMock) -> None:
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_validated_init_data] = _stub_init_data


def _clear_redis_override() -> None:
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_validated_init_data, None)


async def _post_start_expert(mock_redis: AsyncMock) -> None:
    """Hit ``/api/start-expert`` once with a known expert and message."""
    experts = [{"id": "consultant", "name": "Консультант", "emoji": "👷"}]
    _override_redis(mock_redis)
    try:
        with patch("mini_app.api.load_mini_app_config", return_value={"experts": experts}):
            with patch.dict(os.environ, {"BOT_USERNAME": "testbot"}):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={
                            "user_id": 123,
                            "expert_id": "consultant",
                            "message": "Подбери квартиру",
                        },
                    )
        assert resp.status_code == 200, resp.text
    finally:
        _clear_redis_override()


@pytest.mark.asyncio
async def test_start_expert_uses_xadd_to_canonical_stream() -> None:
    """The producer must call XADD on the ``miniapp:start:stream`` key."""
    mock_redis = AsyncMock()
    await _post_start_expert(mock_redis)

    assert mock_redis.xadd.await_count == 1, mock_redis.xadd.await_args_list
    call = mock_redis.xadd.await_args
    # First positional arg (or ``name`` kwarg) is the stream key.
    stream_key = call.args[0] if call.args else call.kwargs.get("name", "")
    assert stream_key == "miniapp:start:stream", call


@pytest.mark.asyncio
async def test_start_expert_xadd_carries_uuid_user_id_query_id() -> None:
    """The XADD fields dict must carry the deep-link tuple the bot needs."""
    mock_redis = AsyncMock()
    await _post_start_expert(mock_redis)

    call = mock_redis.xadd.await_args
    # The fields dict is the second positional arg (or ``fields=`` kwarg).
    fields = call.args[1] if len(call.args) >= 2 else call.kwargs.get("fields", {})
    assert isinstance(fields, dict), fields
    assert "uuid" in fields
    assert fields["user_id"] in (123, "123"), fields  # str or int both fine
    # ``query_id`` was not provided in the request body; it must still be
    # present in the fields (empty string is acceptable) so the consumer
    # always sees the same shape.
    assert "query_id" in fields


@pytest.mark.asyncio
async def test_start_expert_xadd_bounds_stream_with_maxlen() -> None:
    """Stream length must be bounded so a stuck consumer cannot grow it forever."""
    mock_redis = AsyncMock()
    await _post_start_expert(mock_redis)

    call = mock_redis.xadd.await_args
    maxlen = call.kwargs.get("maxlen")
    assert maxlen is not None and maxlen > 0, call.kwargs
    # Approximate trimming is the canonical pattern (much cheaper at high
    # volume than exact MAXLEN=).
    assert call.kwargs.get("approximate") is True, call.kwargs


@pytest.mark.asyncio
async def test_start_expert_does_not_call_legacy_publish() -> None:
    """Migration acceptance gate: the legacy ``PUBLISH`` call is gone."""
    mock_redis = AsyncMock()
    await _post_start_expert(mock_redis)

    # The migration replaces publish with xadd; publish must not be issued.
    assert mock_redis.publish.await_count == 0, mock_redis.publish.await_args_list
