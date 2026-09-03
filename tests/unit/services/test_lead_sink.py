# tests/unit/services/test_lead_sink.py
"""Tests for the durable lead-request sink (#3213).

The phone collector must only confirm a request after an acknowledged sink
write; these tests pin the acknowledgement semantics.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.lead_sink import LeadRequestSink


def _make_redis() -> MagicMock:
    redis = MagicMock()
    pipe = MagicMock()
    pipe.hset = MagicMock()
    pipe.expire = MagicMock()
    pipe_execute = AsyncMock(return_value=[True, True])
    pipe.execute = pipe_execute
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


def _make_bridge(*, sent: bool = True) -> MagicMock:
    bridge = MagicMock()
    bridge.create_topic = AsyncMock(return_value=4242)
    bridge.send_to_topic = AsyncMock(return_value=sent)
    return bridge


async def test_record_persists_to_redis_and_returns_true():
    redis = _make_redis()
    sink = LeadRequestSink(redis=redis)

    ack = await sink.record_request(
        client_id=123,
        phone="+380501234567",
        service_key="viewing",
        username="ivan",
        display_name="Иван П.",
        viewing_objects=[{"id": "obj-1", "complex_name": "Fort Noks"}],
        date_range="nearest",
    )

    assert ack is True
    redis.pipeline.assert_called_once()
    hset_call = redis.pipeline.return_value.hset.call_args
    assert hset_call.args[0] == "lead_request:123"
    mapping = hset_call.kwargs["mapping"]
    assert mapping["phone"] == "+380501234567"
    assert mapping["service_key"] == "viewing"
    assert "obj-1" in mapping["viewing_objects"]
    expire_args = redis.pipeline.return_value.expire.call_args.args
    assert expire_args[0] == "lead_request:123"
    assert expire_args[1] == 72 * 3600


async def test_record_without_redis_or_bridge_is_false():
    """No durable sink configured at all — nothing can be acknowledged."""
    sink = LeadRequestSink(redis=None, forum_bridge=None)

    ack = await sink.record_request(
        client_id=1, phone="+380501234567", service_key="viewing"
    )

    assert ack is False


async def test_record_redis_failure_is_false_and_does_not_raise():
    redis = _make_redis()
    redis.pipeline.return_value.execute = AsyncMock(side_effect=RuntimeError("boom"))
    sink = LeadRequestSink(redis=redis)

    ack = await sink.record_request(client_id=1, phone="+380501234567", service_key="viewing")

    assert ack is False


async def test_record_notifies_managers_when_bridge_configured():
    redis = _make_redis()
    bridge = _make_bridge()
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    ack = await sink.record_request(
        client_id=123,
        phone="+380501234567",
        service_key="viewing",
        display_name="Иван П.",
        date_range="nearest",
    )

    assert ack is True
    bridge.create_topic.assert_awaited_once()
    bridge.send_to_topic.assert_awaited_once()
    text = bridge.send_to_topic.call_args.kwargs["text"]
    assert "+380501234567" in text  # managers need the phone to call back
    assert "viewing" in text
    assert "ближайшие дни" in text


async def test_record_notification_failure_is_false():
    """Configured but failing notification channel must not yield success."""
    redis = _make_redis()
    bridge = _make_bridge(sent=False)
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    ack = await sink.record_request(client_id=1, phone="+380501234567", service_key="viewing")

    assert ack is False


async def test_record_notification_exception_is_false():
    redis = _make_redis()
    bridge = _make_bridge()
    bridge.create_topic = AsyncMock(side_effect=RuntimeError("telegram down"))
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    ack = await sink.record_request(client_id=1, phone="+380501234567", service_key="viewing")

    assert ack is False


async def test_no_raw_phone_in_logs(caplog):
    """Raw phone values must never reach application logs (#3213)."""
    redis = _make_redis()
    bridge = _make_bridge()
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    with caplog.at_level(logging.DEBUG, logger="telegram_bot.services.lead_sink"):
        await sink.record_request(
            client_id=1, phone="+380501234567", service_key="viewing"
        )

    assert all("+380501234567" not in rec.getMessage() for rec in caplog.records)


async def test_date_label_passthrough_for_unknown_key():
    redis = _make_redis()
    bridge = _make_bridge()
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    await sink.record_request(
        client_id=1, phone="+380501234567", service_key="viewing", date_range="custom"
    )

    text = bridge.send_to_topic.call_args.kwargs["text"]
    assert "custom" in text


@pytest.mark.parametrize(
    ("redis_available", "bridge_configured", "bridge_ok", "expected"),
    [
        (True, False, True, True),  # persistence-only deployment
        (True, True, True, True),  # full sink
        (True, True, False, False),  # notification not acked
        (False, True, True, False),  # nothing persisted — not a full ack
        (False, False, True, False),  # no sink at all
    ],
)
async def test_acknowledgement_matrix(redis_available, bridge_configured, bridge_ok, expected):
    redis = _make_redis() if redis_available else None
    bridge = _make_bridge(sent=bridge_ok) if bridge_configured else None
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    ack = await sink.record_request(client_id=1, phone="+380501234567", service_key="viewing")

    assert ack is expected


# --- Lifecycle wiring -------------------------------------------------------


def _wiring_bot(redis_backend: object) -> MagicMock:
    bot = MagicMock()
    bot._cache = MagicMock(redis=redis_backend)
    bot.config.managers_group_id = None
    return bot


def test_setup_handoff_services_wires_lead_sink():
    from telegram_bot.lifecycle.lifecycle import setup_handoff_services

    redis = object()
    bot = _wiring_bot(redis)

    setup_handoff_services(bot)

    assert isinstance(bot._lead_sink, LeadRequestSink)
    assert bot._lead_sink._redis is redis


def test_setup_workflow_data_registers_lead_sink_for_handlers():
    from telegram_bot.lifecycle.lifecycle import setup_handoff_services, setup_workflow_data

    bot = _wiring_bot(object())
    bot._i18n_hub = None  # skip i18n middleware branch — not under test here
    bot._lead_sink = None

    setup_handoff_services(bot)
    setup_workflow_data(bot)

    registered = {
        call.args[0]: call.args[1] for call in bot.dp.__setitem__.call_args_list
    }
    assert registered["lead_sink"] is bot._lead_sink
    assert isinstance(registered["lead_sink"], LeadRequestSink)


def test_setup_handoff_services_without_redis_leaves_sink_absent():
    from telegram_bot.lifecycle.lifecycle import setup_handoff_services

    bot = _wiring_bot(None)
    bot._lead_sink = None

    setup_handoff_services(bot)

    assert bot._lead_sink is None
