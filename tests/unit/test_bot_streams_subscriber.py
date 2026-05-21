# tests/unit/test_bot_streams_subscriber.py
"""Consumer-side contract for the Mini App deep-link Redis Streams migration.

Issue #1239 replaces the volatile pub/sub subscriber in
``PropertyBot._miniapp_subscriber_loop`` with a Redis Streams consumer
group so:

* messages are acknowledged after processing (``XACK``),
* messages missed during a bot restart can be replayed,
* poison entries with malformed fields don't redeliver forever.

This module pins five behaviours of the migrated loop using
``fakeredis.aioredis`` for end-to-end stream semantics:

1. The consumer group ``miniapp-bot`` is created with ``MKSTREAM=True``.
2. A duplicate run swallows ``BUSYGROUP`` from ``XGROUP CREATE``.
3. New stream entries are dispatched to ``_process_miniapp_start``.
4. Successfully processed entries are ``XACK``-ed (PEL becomes empty).
5. Stream entries with missing required fields are skipped *and* acked
   (no re-delivery storm).

Pending-replay-on-startup is exercised by feeding entries before the
loop starts and asserting they are still picked up — confirming the
``id='0'`` recovery path runs at least once before steady-state
``id='>'`` loop.

Refs #1239. Context7 source for the API:
``/redis/redis-py`` docs/examples/redis-stream-example.ipynb +
docs/commands.md#xreadgroup.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")
pytest.importorskip("fakeredis", reason="fakeredis not installed in this env")

from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


_STREAM = "miniapp:start:stream"
_GROUP = "miniapp-bot"
_CONSUMER = "bot-default"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config(monkeypatch):
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("KOMMO_ACCESS_TOKEN", raising=False)
    return BotConfig(
        _env_file=None,
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        realestate_database_url="postgresql://postgres:postgres@127.0.0.1:1/realestate",
        rerank_provider="none",
    )


def _create_bot(mock_config):
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(mock_config)


@pytest.fixture
def fake_redis():
    """A fresh ``fakeredis.aioredis`` instance per test."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def _prepare_stream(fake: fakeredis.aioredis.FakeRedis) -> None:
    """Create the consumer group with cursor at the start of the stream.

    Tests that pre-add entries before running the loop need the group's
    delivery cursor to be at ``0`` so the next ``XREADGROUP`` with the
    ``">"`` cursor will see those entries. The loop's own
    ``XGROUP CREATE id="$"`` would otherwise position the cursor past
    them, making the test vacuously pass. The loop's create call returns
    ``BUSYGROUP`` (which is swallowed) on top of this pre-creation.
    """
    await fake.xgroup_create(name=_STREAM, groupname=_GROUP, id="0", mkstream=True)


async def _run_loop_briefly(bot: PropertyBot, fake: fakeredis.aioredis.FakeRedis) -> None:
    """Patch ``redis.asyncio.from_url`` to return ``fake`` and run the loop briefly."""
    with patch("redis.asyncio.from_url", return_value=fake):
        task = asyncio.create_task(bot._miniapp_subscriber_loop())
        # Give the loop time to xreadgroup at least once. The block timeout
        # in the loop must be short enough that this sleep covers it.
        await asyncio.sleep(0.1)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


class TestSubscriberStreamsContract:
    @pytest.mark.asyncio
    async def test_consumer_group_is_created_with_mkstream_on_startup(
        self, mock_config, fake_redis
    ):
        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock()

        await _run_loop_briefly(bot, fake_redis)

        # The group must exist after the loop starts.
        groups = await fake_redis.xinfo_groups(_STREAM)
        names = {g["name"] for g in groups}
        assert _GROUP in names, groups

    @pytest.mark.asyncio
    async def test_busygroup_on_second_run_does_not_crash(self, mock_config, fake_redis):
        # Pre-create the group so the loop's xgroup_create raises BUSYGROUP.
        await fake_redis.xgroup_create(name=_STREAM, groupname=_GROUP, id="$", mkstream=True)

        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock()

        # Should not raise even though xgroup_create returns BUSYGROUP.
        await _run_loop_briefly(bot, fake_redis)

    @pytest.mark.asyncio
    async def test_entry_dispatches_to_process_miniapp_start(self, mock_config, fake_redis):
        # Pre-create group with cursor at 0 so the xadd below is visible to
        # the loop's ">"-cursor read. The loop's own xgroup_create returns
        # BUSYGROUP and is swallowed.
        await _prepare_stream(fake_redis)
        await fake_redis.xadd(
            _STREAM,
            {"uuid": "abc-123", "user_id": "456", "query_id": ""},
            maxlen=1000,
            approximate=True,
        )

        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock()

        await _run_loop_briefly(bot, fake_redis)

        bot._process_miniapp_start.assert_awaited_once()
        kwargs = bot._process_miniapp_start.await_args.kwargs
        assert kwargs.get("chat_id") == 456
        assert kwargs.get("uuid_str") == "abc-123"

    @pytest.mark.asyncio
    async def test_processed_entries_are_acked(self, mock_config, fake_redis):
        await _prepare_stream(fake_redis)
        await fake_redis.xadd(
            _STREAM,
            {"uuid": "abc", "user_id": "1"},
            maxlen=1000,
            approximate=True,
        )

        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock()

        await _run_loop_briefly(bot, fake_redis)

        # Processor must have been called for the visible entry...
        bot._process_miniapp_start.assert_awaited_once()
        # ...and the entry must have been acked (PEL is empty).
        pending = await fake_redis.xpending(_STREAM, _GROUP)
        assert pending["pending"] == 0, pending

    @pytest.mark.asyncio
    async def test_poison_entry_is_skipped_and_acked(self, mock_config, fake_redis):
        await _prepare_stream(fake_redis)
        # A "poison" entry: missing required `user_id` field.
        await fake_redis.xadd(
            _STREAM,
            {"uuid": "abc", "missing_user_id_field": "yes"},
            maxlen=1000,
            approximate=True,
        )

        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock()

        await _run_loop_briefly(bot, fake_redis)

        # The processor must NOT have been called for the poison entry...
        bot._process_miniapp_start.assert_not_called()
        # ...but it must have been acked so it is not redelivered forever.
        pending = await fake_redis.xpending(_STREAM, _GROUP)
        assert pending["pending"] == 0, pending

    @pytest.mark.asyncio
    async def test_processing_error_does_not_ack(self, mock_config, fake_redis):
        """A transient processing error leaves the entry in the PEL for retry."""
        await _prepare_stream(fake_redis)
        await fake_redis.xadd(
            _STREAM,
            {"uuid": "abc", "user_id": "1"},
            maxlen=1000,
            approximate=True,
        )

        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock(
            side_effect=RuntimeError("transient downstream error")
        )

        await _run_loop_briefly(bot, fake_redis)

        # Processor was called (and crashed)...
        bot._process_miniapp_start.assert_awaited_once()
        # ...so the message stays pending for redelivery.
        pending = await fake_redis.xpending(_STREAM, _GROUP)
        assert pending["pending"] >= 1, pending

    @pytest.mark.asyncio
    async def test_pending_replay_drains_more_than_one_batch(self, mock_config, fake_redis):
        """Startup replay must drain all pending entries for this consumer."""
        await _prepare_stream(fake_redis)
        for idx in range(12):
            await fake_redis.xadd(
                _STREAM,
                {"uuid": f"abc-{idx}", "user_id": str(idx + 1)},
                maxlen=1000,
                approximate=True,
            )

        # Simulate a previous bot run that read the messages but crashed
        # before acking them. The next run must replay more than one BATCH.
        delivered = await fake_redis.xreadgroup(
            groupname=_GROUP,
            consumername=_CONSUMER,
            streams={_STREAM: ">"},
            count=12,
        )
        assert sum(len(entries) for _stream, entries in delivered) == 12

        bot = _create_bot(mock_config)
        bot._topic_manager = MagicMock()
        bot._process_miniapp_start = AsyncMock()

        await _run_loop_briefly(bot, fake_redis)

        assert bot._process_miniapp_start.await_count == 12
        pending = await fake_redis.xpending(_STREAM, _GROUP)
        assert pending["pending"] == 0, pending
