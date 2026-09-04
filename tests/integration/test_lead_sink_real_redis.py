"""Live Redis durability contract for the lead sink (#3322).

Runs against a real Redis when one is reachable (skips otherwise) and
covers the versioned durability contract end-to-end:

- new v2 record persists under ``lead_request:v2:{client}``;
- a pre-existing legacy ``lead_request:{client}`` hash is untouched by v2
  writes and still readable after them;
- mixed listing merges legacy + v2 without rewriting the legacy hash;
- a rollback-era reader of the legacy key never sees v2 records;
- retry of the same request id is idempotent on the live server.

Artifacts are limited to the unique ``i3322-`` client ids and are deleted
in ``finally`` teardown; nothing else in the shared Redis instance is
touched. No ``FLUSH*`` or wildcard deletion is used anywhere.
"""

from __future__ import annotations

import json

import pytest
import redis.asyncio as aioredis

from telegram_bot.services.lead_sink import LeadRequestSink


pytestmark = pytest.mark.requires_services

_CLIENT_NEW = 33220001
_CLIENT_LEGACY = 33220002
_CLIENT_MIXED = 33220003
_LEGACY_KEY = f"lead_request:{_CLIENT_LEGACY}"
_MIXED_LEGACY_KEY = f"lead_request:{_CLIENT_MIXED}"
_V2_KEYS = (
    f"lead_request:v2:{_CLIENT_NEW}",
    f"lead_request:v2:{_CLIENT_LEGACY}",
    f"lead_request:v2:{_CLIENT_MIXED}",
)
_OWNED_KEYS = (_LEGACY_KEY, _MIXED_LEGACY_KEY, *_V2_KEYS)


async def _redis_reachable(url: str) -> bool:
    """Probe with a real PING: TCP-open but unauthorized/not-Redis skips."""
    client = aioredis.from_url(url, decode_responses=True, socket_timeout=2.0)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


async def test_lead_sink_v2_durability_on_real_redis(redis_url: str) -> None:
    if not await _redis_reachable(redis_url):
        pytest.skip("Redis is not reachable on the configured URL")

    client = aioredis.from_url(redis_url, decode_responses=True)
    sink = LeadRequestSink(redis=client)
    request_id = f"i3322-{_CLIENT_NEW}-req"
    try:
        # --- New: v2 write lands under the versioned namespace -------------
        assert await sink.record_request(
            client_id=_CLIENT_NEW,
            request_id=request_id,
            phone="+359885000001",
            service_key="viewing",
        )
        raw_v2 = await client.hgetall(f"lead_request:v2:{_CLIENT_NEW}")
        assert request_id in raw_v2
        record = json.loads(raw_v2[request_id])
        assert record["phone"] == "+359885000001"
        assert record["request_id"] == request_id

        # --- Retry idempotency: same id does not duplicate -----------------
        assert await sink.record_request(
            client_id=_CLIENT_NEW,
            request_id=request_id,
            phone="+359885000001",
            service_key="viewing",
        )
        raw_v2 = await client.hgetall(f"lead_request:v2:{_CLIENT_NEW}")
        assert list(raw_v2) == [request_id]

        # --- Legacy: pre-existing key survives v2 writes untouched ---------
        legacy_fields = {"client_id": str(_CLIENT_LEGACY), "phone": "+359885000002"}
        for field, value in legacy_fields.items():
            await client.hset(_LEGACY_KEY, field, value)
        assert await sink.record_request(
            client_id=_CLIENT_LEGACY,
            request_id="i3322-legacy-client-req",
            phone="+359885000003",
            service_key="viewing",
        )
        after = await client.hgetall(_LEGACY_KEY)
        assert after == legacy_fields  # not rewritten, not deleted

        # --- Rollback read: a pre-v2 reader sees only the legacy hash ------
        rollback_view = await client.hgetall(f"lead_request:{_CLIENT_NEW}")
        assert rollback_view == {}

        # --- Mixed listing: legacy + v2 merged, legacy still readable ------
        for field, value in legacy_fields.items():
            await client.hset(_MIXED_LEGACY_KEY, field, value)
        assert await sink.record_request(
            client_id=_CLIENT_MIXED,
            request_id="i3322-mixed-req",
            phone="+359885000004",
            service_key="viewing",
        )
        records = await sink.list_requests(_CLIENT_MIXED)
        versions = sorted(r.get("record_version") for r in records)
        assert versions == ["legacy", "v2"]
        legacy_record = next(r for r in records if r["record_version"] == "legacy")
        assert legacy_record["phone"] == "+359885000002"

        # Legacy key remains byte-identical after the merged listing.
        assert await client.hgetall(_MIXED_LEGACY_KEY) == legacy_fields
    finally:
        # Exact run-owned key cleanup only — never FLUSH* or wildcards.
        for key in _OWNED_KEYS:
            await client.delete(key)
        await client.aclose()
