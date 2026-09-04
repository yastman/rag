# tests/unit/services/test_lead_sink.py
"""Tests for the durable lead-request sink (#3213, #3322).

The phone collector must only confirm a request after an acknowledged sink
write; these tests pin the acknowledgement semantics and the versioned
append-only durability contract:

- v2 records live under ``lead_request:v2:{client_id}`` keyed by the
  boundary-owned ``request_id``; retries are idempotent (HSETNX) and
  distinct ids coexist;
- the pre-v2 ``lead_request:{client_id}`` hash is never written, rewritten
  or deleted; listings merge it read-only;
- a rollback-era reader of the legacy key never sees v2 records.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.lead_sink import LeadRequestSink


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def hsetnx(self, key: str, field: str, value: str) -> _FakePipeline:
        self._ops.append(("hsetnx", key, field, value))
        return self

    def hset(self, key: str, mapping: dict) -> _FakePipeline:
        self._ops.append(("hset", key, dict(mapping)))
        return self

    def expire(self, key: str, ttl: int) -> _FakePipeline:
        self._ops.append(("expire", key, ttl))
        return self

    async def execute(self) -> list[Any]:
        if self._redis.fail:
            raise RuntimeError("boom")
        results: list[Any] = []
        for op in self._ops:
            if op[0] == "hsetnx":
                _, key, field, value = op
                fields = self._redis.hashes.setdefault(key, {})
                added = field not in fields
                results.append(added)
                if added:
                    fields[field] = value
            elif op[0] == "hset":
                _, key, mapping = op
                fields = self._redis.hashes.setdefault(key, {})
                fields.update(mapping)
                results.append(True)
            else:
                _, key, ttl = op
                self._redis.expires.append((key, ttl))
                results.append(True)
        return results


class _FakeRedis:
    """Minimal hash/pipeline Redis stand-in with real HSETNX semantics."""

    def __init__(self, *, fail: bool = False) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires: list[tuple[str, int]] = []
        self.fail = fail

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    async def hgetall(self, key: str) -> dict[str, str]:
        if self.fail:
            raise RuntimeError("redis down")
        return dict(self.hashes.get(key, {}))


def _make_redis(*, fail: bool = False) -> _FakeRedis:
    return _FakeRedis(fail=fail)


def _make_bridge(*, sent: bool = True) -> MagicMock:
    bridge = MagicMock()
    bridge.create_topic = AsyncMock(return_value=4242)
    bridge.send_to_topic = AsyncMock(return_value=sent)
    return bridge


def _record_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "client_id": 123,
        "request_id": "req-1",
        "phone": "+380501234567",
        "service_key": "viewing",
        "username": "ivan",
        "display_name": "Иван П.",
        "viewing_objects": [{"id": "obj-1", "complex_name": "Fort Noks"}],
        "date_range": "nearest",
    }
    kwargs.update(overrides)
    return kwargs


async def test_record_persists_to_v2_hash_and_returns_true():
    redis = _make_redis()
    sink = LeadRequestSink(redis=redis)

    ack = await sink.record_request(**_record_kwargs())

    assert ack is True
    v2_key = "lead_request:v2:123"
    fields = redis.hashes[v2_key]
    assert set(fields) == {"req-1"}
    record = json.loads(fields["req-1"])
    assert record["phone"] == "+380501234567"
    assert record["service_key"] == "viewing"
    assert record["request_id"] == "req-1"
    assert "obj-1" in record["viewing_objects"]
    assert ("lead_request:v2:123", 72 * 3600) in redis.expires
    # The legacy namespace is never written by v2.
    assert "lead_request:123" not in redis.hashes


async def test_record_without_redis_or_bridge_is_false():
    """No durable sink configured at all — nothing can be acknowledged."""
    sink = LeadRequestSink(redis=None, forum_bridge=None)

    ack = await sink.record_request(
        client_id=1, request_id="req-1", phone="+380501234567", service_key="viewing"
    )

    assert ack is False


async def test_record_redis_failure_is_false_and_does_not_raise():
    redis = _make_redis(fail=True)
    sink = LeadRequestSink(redis=redis)

    ack = await sink.record_request(
        client_id=1, request_id="req-1", phone="+380501234567", service_key="viewing"
    )

    assert ack is False


async def test_record_requires_stable_request_id():
    """A missing request id is a boundary programming error, not a silent write."""
    sink = LeadRequestSink(redis=_make_redis())

    with pytest.raises(ValueError):
        await sink.record_request(
            client_id=1, request_id="", phone="+380501234567", service_key="viewing"
        )


async def test_record_notifies_managers_when_bridge_configured():
    redis = _make_redis()
    bridge = _make_bridge()
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    ack = await sink.record_request(**_record_kwargs())

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

    ack = await sink.record_request(
        client_id=1, request_id="req-1", phone="+380501234567", service_key="viewing"
    )

    assert ack is False


async def test_record_notification_exception_is_false():
    redis = _make_redis()
    bridge = _make_bridge()
    bridge.create_topic = AsyncMock(side_effect=RuntimeError("telegram down"))
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    ack = await sink.record_request(
        client_id=1, request_id="req-1", phone="+380501234567", service_key="viewing"
    )

    assert ack is False


async def test_no_raw_phone_in_logs(caplog):
    """Raw phone values must never reach application logs (#3213)."""
    redis = _make_redis()
    bridge = _make_bridge()
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    with caplog.at_level(logging.DEBUG, logger="telegram_bot.services.lead_sink"):
        await sink.record_request(
            client_id=1, request_id="req-1", phone="+380501234567", service_key="viewing"
        )

    assert all("+380501234567" not in rec.getMessage() for rec in caplog.records)


async def test_date_label_passthrough_for_unknown_key():
    redis = _make_redis()
    bridge = _make_bridge()
    sink = LeadRequestSink(redis=redis, forum_bridge=bridge)

    await sink.record_request(
        client_id=1,
        request_id="req-1",
        phone="+380501234567",
        service_key="viewing",
        date_range="custom",
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

    ack = await sink.record_request(
        client_id=1, request_id="req-1", phone="+380501234567", service_key="viewing"
    )

    assert ack is expected


# --- Versioned durability contract (#3322) ---------------------------------


async def test_two_distinct_requests_coexist_and_retry_is_idempotent():
    redis = _make_redis()
    sink = LeadRequestSink(redis=redis)

    assert await sink.record_request(**_record_kwargs(request_id="req-1")) is True
    assert await sink.record_request(**_record_kwargs(request_id="req-2")) is True

    fields = redis.hashes["lead_request:v2:123"]
    assert set(fields) == {"req-1", "req-2"}

    # Retry of the first logical request: no duplicate, first write wins.
    first_created_at = json.loads(fields["req-1"])["created_at"]
    await sink.record_request(**_record_kwargs(request_id="req-1"))
    fields = redis.hashes["lead_request:v2:123"]
    assert set(fields) == {"req-1", "req-2"}
    assert json.loads(fields["req-1"])["created_at"] == first_created_at


def _seed_legacy(redis: _FakeRedis, client_id: int = 123) -> None:
    redis.hashes[f"lead_request:{client_id}"] = {
        "client_id": str(client_id),
        "phone": "+380501234000",
        "service_key": "viewing",
        "created_at": "1700000000",
    }


async def test_legacy_key_survives_rollout_and_listings_merge_it():
    redis = _make_redis()
    legacy_before = dict(redis.hashes.get("lead_request:123", {}))
    _seed_legacy(redis)
    legacy_before = dict(redis.hashes["lead_request:123"])
    sink = LeadRequestSink(redis=redis)

    await sink.record_request(**_record_kwargs(request_id="req-new"))
    records = await sink.list_requests(123)

    assert len(records) == 2
    legacy = next(r for r in records if r.get("record_version") == "legacy")
    v2 = next(r for r in records if r.get("record_version") == "v2")
    assert legacy["phone"] == "+380501234000"
    assert legacy["request_id"] == "legacy"
    assert v2["request_id"] == "req-new"
    # The legacy hash is untouched: byte-identical content, no new TTL entry.
    assert redis.hashes["lead_request:123"] == legacy_before
    assert all(key != "lead_request:123" for key, _ttl in redis.expires)


async def test_rollback_reader_never_sees_v2_as_legacy():
    """A pre-v2 reader of the legacy key must not observe v2 records (#3322)."""
    redis = _make_redis()
    _seed_legacy(redis)
    sink = LeadRequestSink(redis=redis)
    await sink.record_request(**_record_kwargs(request_id="req-new"))

    legacy_view = await redis.hgetall("lead_request:123")

    assert set(legacy_view) == {"client_id", "phone", "service_key", "created_at"}
    assert "req-new" not in legacy_view


async def test_ttl_write_targets_only_the_v2_key():
    redis = _make_redis()
    _seed_legacy(redis)
    sink = LeadRequestSink(redis=redis)

    await sink.record_request(**_record_kwargs(request_id="req-1"))
    await sink.record_request(**_record_kwargs(request_id="req-2"))

    expire_keys = {key for key, _ttl in redis.expires}
    assert expire_keys == {"lead_request:v2:123"}
    # Coexisting records survive each other's TTL writes.
    assert set(redis.hashes["lead_request:v2:123"]) == {"req-1", "req-2"}


async def test_listing_fails_closed_when_redis_is_down():
    redis = _make_redis(fail=True)
    sink = LeadRequestSink(redis=redis)

    assert await sink.list_requests(123) == []


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

    registered = {call.args[0]: call.args[1] for call in bot.dp.__setitem__.call_args_list}
    assert registered["lead_sink"] is bot._lead_sink
    assert isinstance(registered["lead_sink"], LeadRequestSink)


def test_setup_handoff_services_without_redis_leaves_sink_absent():
    from telegram_bot.lifecycle.lifecycle import setup_handoff_services

    bot = _wiring_bot(None)
    bot._lead_sink = None

    setup_handoff_services(bot)

    assert bot._lead_sink is None
