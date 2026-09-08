"""Durable lead-request sink for phone-collected requests (#3213, #3322, #3477).

The phone collector (#628) used to confirm "заявка оформлена" without any
durable write or manager notification. This module is the observable sink
behind that confirmation:

- **Persistence** — each request is written to the versioned Redis hash
  ``lead_request:v2:{client_id}`` with the caller-provided ``request_id`` as
  the hash field and a TTL. Distinct requests coexist as distinct fields and
  a retry of the same ``request_id`` is a no-op (HSETNX), so the first
  acknowledgement is the record (#3322).
- **Manager notification** — when the Forum Topics bridge is configured, a
  dedicated topic is created in the managers group and the request details
  (including the phone number managers need to call back) are posted there.
  The side effect is gated on acknowledged persistence (#3477): a request
  the sink could not save never reaches managers, and the message is
  rendered from the persisted record — the payload authority — not from the
  caller's kwargs.

Legacy compatibility (#3322): the pre-v2 sink overwrote the single hash
``lead_request:{client_id}`` per client. During the compatibility window
that key is never written, rewritten, or deleted by this module;
:meth:`LeadRequestSink.list_requests` merges its contents into the v2
listing read-only. The v2 namespace lives under a different key, so a
pre-v2 reader observing ``lead_request:{client_id}`` never sees v2 records.
Notification state (below) lives in its own namespace and is never part of
record listings.

``record_request`` returns ``True`` only when persistence is acknowledged
and, if the notification channel is configured, the notification is also
acknowledged. Callers must gate success copy on that acknowledgement:
never confirm a request that no sink observed (#3213).

Notification identity policy (bounded, #3477): every ``(client_id,
request_id)`` pair has one durable notification state under
``lead_notify:v2:{client_id}`` — the same versioned-hash + TTL design as
the v2 record. Fresh attempts claim that state atomically (HSETNX), so
concurrent same-id retries have exactly one creator; losers report False
without side effects and may retry later. A claim that already holds a
topic id always resumes that topic — topic creation is at-most-once per
durable claim, delivery per topic is at-least-once. A claim without a
topic that is older than the bounded lease (:data:`_CLAIM_LEASE_SECONDS`)
is treated as crashed and taken over; the takeover itself is not mutually
exclusive, so concurrent recoveries of the same crashed attempt may each
create one topic. Remote outcomes that could not be recorded durably
(Redis failure between the Telegram side effect and the state write) are
reported as ``False`` and logged — observable, never silent; a later
bounded retry may then create one extra topic or repeat one message.
Exactly-once across Redis and Telegram is NOT guaranteed: the guarantees
are — no notification without acknowledged persistence, no repeated
known-acknowledged work, and no untracked side effects. Dedup state
shares the record TTL horizon; after expiry a re-issued request id is
treated as new.

Privacy: raw phone values are never written to application logs — they
exist only in the durable record and the manager notification.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import TypeAdapter

from telegram_bot.services.forum_bridge import ForumBridge


logger = logging.getLogger(__name__)

_LEGACY_PREFIX = "lead_request"
_V2_PREFIX = "lead_request:v2"
_NOTIFY_V2_PREFIX = "lead_notify:v2"
_OBJECTS_ADAPTER = TypeAdapter(list[dict[str, Any]])

# A "sending" claim without a recorded topic older than this is treated as
# crashed; a retry takes it over (bounded recovery — see module docstring).
_CLAIM_LEASE_SECONDS = 120

# Mirrors dialogs.viewing.DATE_LABELS (kept local to avoid a services →
# dialogs import); unknown keys pass through raw.
_DATE_LABELS: dict[str, str] = {
    "nearest": "ближайшие дни",
    "next_week": "через неделю",
    "next_month": "через месяц",
    "unknown": "не знаю когда",
    "phone": "согласуем по телефону",
}


def _date_label(date_range: str | None) -> str | None:
    if not date_range:
        return None
    return _DATE_LABELS.get(date_range, date_range)


def _format_objects(viewing_objects: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for obj in viewing_objects:
        if not isinstance(obj, dict):
            continue
        parts = [
            str(obj.get("complex_name") or "").strip(),
            str(obj.get("property_type") or "").strip(),
        ]
        area = obj.get("area_m2")
        if area:
            parts.append(f"{area} м²")
        price = obj.get("price_eur")
        if price:
            parts.append(f"{price} €")
        title = " · ".join(p for p in parts if p)
        obj_id = obj.get("id")
        lines.append(f"• {title} (id={obj_id})" if title else f"• id={obj_id}")
    return lines


def _decode(value: Any) -> str:
    """Decode a Redis reply (bytes or str) to str."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _render_notification(record: dict[str, Any]) -> str:
    """Render the manager message from the persisted v2 record (#3477).

    The record is the payload authority: retries of the same request speak
    the first persisted payload, never a later retry's kwargs.
    """
    phone = str(record.get("phone") or "")
    service_key = str(record.get("service_key") or "")
    username = str(record.get("username") or "")
    viewing_objects: list[Any] = []
    raw_objects = record.get("viewing_objects")
    if isinstance(raw_objects, str) and raw_objects:
        try:
            parsed = json.loads(raw_objects)
        except (ValueError, TypeError):
            parsed = []
        viewing_objects = parsed if isinstance(parsed, list) else []
    elif isinstance(raw_objects, list):
        viewing_objects = raw_objects
    lines = ["--- Новая заявка ---"]
    lines.append(f"Телефон: {phone}")
    lines.append(f"Тип: {service_key}")
    if username:
        lines.append(f"Telegram: @{username}")
    when = _date_label(str(record.get("date_range") or "") or None)
    if when:
        lines.append(f"Когда: {when}")
    object_lines = _format_objects(viewing_objects)
    if object_lines:
        lines.append("Объекты:")
        lines.extend(object_lines)
    lines.append("---")
    return "\n".join(lines)


class LeadRequestSink:
    """Persist lead requests durably and notify managers when possible."""

    def __init__(
        self,
        *,
        redis: Any,
        forum_bridge: ForumBridge | None = None,
        ttl_hours: int = 72,
    ) -> None:
        self._redis = redis
        self._forum_bridge = forum_bridge
        self._ttl = ttl_hours * 3600

    async def record_request(
        self,
        *,
        client_id: int,
        request_id: str,
        phone: str,
        service_key: str,
        username: str | None = None,
        display_name: str = "",
        viewing_objects: list[dict[str, Any]] | None = None,
        date_range: str | None = None,
    ) -> bool:
        """Record a request. Returns True only after acknowledged sink writes.

        ``request_id`` is owned by the confirmation/FSM boundary and must be
        stable across retries of the same logical request (#3322): the v2
        write is HSETNX, so a retry of an already-recorded id is a no-op and
        distinct ids coexist.

        Persistence (Redis) is attempted first. If it is not acknowledged,
        this method returns False before any manager side effect (#3477).
        If the Forum Topics bridge is configured, the notification is then
        handled under the per-request identity policy (module docstring):
        already-acknowledged notifications are skipped, known topics are
        reused, and the message payload comes from the persisted record.
        """
        if not request_id:
            raise ValueError("request_id is required for durable lead persistence")
        objects = viewing_objects or []
        persisted = await self._persist(
            client_id=client_id,
            request_id=request_id,
            phone=phone,
            service_key=service_key,
            username=username,
            display_name=display_name,
            viewing_objects=objects,
            date_range=date_range,
        )
        if not persisted:
            # #3477: no manager side effect for a request the client is
            # (correctly) told was not saved.
            return False
        if self._forum_bridge is None:
            return True
        record = await self._load_record(client_id, request_id)
        if record is None:
            logger.warning(
                "Lead request record unreadable after persistence; refusing "
                "untracked notification: request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        return await self._notify(client_id=client_id, request_id=request_id, record=record)

    async def list_requests(self, client_id: int) -> list[dict[str, Any]]:
        """List a client's records: v2 fields merged with the legacy record.

        Read-only compatibility view (#3322): the legacy
        ``lead_request:{client_id}`` hash is returned as one legacy record and
        is never rewritten or deleted. On any Redis failure the listing is
        empty — callers must not treat a failed listing as an empty history.
        """
        if self._redis is None:
            return []
        records: list[dict[str, Any]] = []
        try:
            legacy = await self._redis.hgetall(f"{_LEGACY_PREFIX}:{client_id}")
            if legacy:
                record = {_decode(k): _decode(v) for k, v in legacy.items()}
                record.setdefault("request_id", "legacy")
                record["record_version"] = "legacy"
                records.append(record)
            v2 = await self._redis.hgetall(f"{_V2_PREFIX}:{client_id}")
            for raw in v2.values():
                try:
                    record = json.loads(_decode(raw))
                except (ValueError, TypeError):
                    logger.warning(
                        "Lead request v2 record is not valid JSON; skipped: user=%s",
                        client_id,
                    )
                    continue
                if isinstance(record, dict):
                    record.setdefault("record_version", "v2")
                    records.append(record)
        except Exception as exc:
            logger.warning(
                "Lead request listing failed (fail closed): %s: %s",
                type(exc).__name__,
                exc,
            )
            return []
        records.sort(key=lambda r: str(r.get("created_at") or ""))
        return records

    async def _persist(
        self,
        *,
        client_id: int,
        request_id: str,
        phone: str,
        service_key: str,
        username: str | None,
        display_name: str,
        viewing_objects: list[dict[str, Any]],
        date_range: str | None,
    ) -> bool:
        if self._redis is None:
            return False
        record = {
            "client_id": str(client_id),
            "request_id": request_id,
            "phone": phone,
            "service_key": service_key,
            "username": username or "",
            "display_name": display_name,
            "viewing_objects": _OBJECTS_ADAPTER.dump_json(viewing_objects).decode(),
            "date_range": date_range or "",
            "created_at": str(int(time.time())),
        }
        key = f"{_V2_PREFIX}:{client_id}"
        try:
            pipe = self._redis.pipeline()
            # HSETNX keeps retries of the same request_id idempotent: the
            # first acknowledged write wins, later retries change nothing.
            pipe.hsetnx(key, request_id, json.dumps(record, ensure_ascii=False))
            pipe.expire(key, self._ttl)
            await pipe.execute()
        except Exception:
            logger.warning(
                "Lead request persistence failed: service_key=%s user=%s",
                service_key,
                client_id,
            )
            return False
        return True

    async def _load_record(self, client_id: int, request_id: str) -> dict[str, Any] | None:
        """Read the persisted v2 record — the notification payload authority."""
        if self._redis is None:
            return None
        try:
            raw = await self._redis.hgetall(f"{_V2_PREFIX}:{client_id}")
        except Exception:
            return None
        value = None
        for field, candidate in raw.items():
            if _decode(field) == request_id:
                value = candidate
                break
        if value is None:
            return None
        try:
            record = json.loads(_decode(value))
        except (ValueError, TypeError):
            return None
        return record if isinstance(record, dict) else None

    async def _load_notify_state(
        self, client_id: int, request_id: str
    ) -> tuple[str, dict[str, Any]]:
        """Load the per-request notification state (#3477).

        Returns ``(kind, state)`` where ``kind`` is:

        - ``"absent"`` — no state recorded yet;
        - ``"ready"`` — parseable state dict;
        - ``"corrupt"`` — a field exists but cannot be parsed (treated as
          unknown and taken over on the next claim);
        - ``"unavailable"`` — Redis failed: durable tracking is impossible
          right now, so no side effect may be fired.
        """
        try:
            raw = await self._redis.hgetall(f"{_NOTIFY_V2_PREFIX}:{client_id}")
        except Exception:
            return "unavailable", {}
        value = None
        for field, candidate in raw.items():
            if _decode(field) == request_id:
                value = candidate
                break
        if value is None:
            return "absent", {}
        try:
            state = json.loads(_decode(value))
        except (ValueError, TypeError):
            return "corrupt", {}
        if not isinstance(state, dict):
            return "corrupt", {}
        return "ready", state

    @staticmethod
    def _claim_stale(state: dict[str, Any]) -> bool:
        """True when a "sending" claim is older than the bounded lease."""
        updated_at = state.get("updated_at")
        if updated_at is None:
            return True
        try:
            age = time.time() - float(updated_at)
        except (TypeError, ValueError):
            return True
        return age > _CLAIM_LEASE_SECONDS

    async def _claim_notify(
        self,
        client_id: int,
        request_id: str,
        *,
        topic_id: int | None,
        takeover: bool,
    ) -> bool:
        """Claim or overwrite the per-request notification state (#3477).

        A fresh claim uses HSETNX: concurrent same-id attempts have exactly
        one atomic winner. A takeover (stale/corrupt state, or a state that
        already holds a known topic) overwrites the field; it is not mutually
        exclusive — bounded, see the module docstring.
        """
        entry = {
            "status": "sending",
            "topic_id": topic_id,
            "updated_at": int(time.time()),
        }
        key = f"{_NOTIFY_V2_PREFIX}:{client_id}"
        try:
            pipe = self._redis.pipeline()
            if takeover:
                pipe.hset(key, mapping={request_id: json.dumps(entry, ensure_ascii=False)})
            else:
                pipe.hsetnx(key, request_id, json.dumps(entry, ensure_ascii=False))
            pipe.expire(key, self._ttl)
            results = await pipe.execute()
        except Exception:
            logger.warning(
                "Lead notification state write failed: request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        # A falsy first result on a fresh claim means the field appeared
        # between our read and the claim: another attempt won the race.
        return bool(takeover or not results or results[0])

    async def _write_notify_state(
        self,
        client_id: int,
        request_id: str,
        *,
        status: str,
        topic_id: int | None,
    ) -> bool:
        entry: dict[str, Any] = {
            "status": status,
            "topic_id": topic_id,
            "updated_at": int(time.time()),
        }
        if status == "notified":
            entry["notified"] = True
            entry["notified_at"] = entry["updated_at"]
        key = f"{_NOTIFY_V2_PREFIX}:{client_id}"
        try:
            pipe = self._redis.pipeline()
            pipe.hset(
                key,
                mapping={request_id: json.dumps(entry, ensure_ascii=False)},
            )
            pipe.expire(key, self._ttl)
            await pipe.execute()
        except Exception:
            return False
        return True

    async def _notify(self, *, client_id: int, request_id: str, record: dict[str, Any]) -> bool:
        """Deliver the manager notification under the #3477 identity policy.

        One durable notification identity per ``(client_id, request_id)``:
        fresh claims are atomic (single creator), a known topic is resumed —
        never re-created — and an already-acknowledged notification is
        skipped. Remote outcomes that cannot be recorded durably are logged
        and reported as False; delivery per topic is at-least-once, topic
        creation per durable claim is at-most-once. See the module
        docstring for the full bounded policy.
        """
        bridge = self._forum_bridge
        if bridge is None:
            return False
        kind, state = await self._load_notify_state(client_id, request_id)
        if kind == "unavailable":
            logger.warning(
                "Lead notification state unavailable; refusing untracked side "
                "effect: request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        known_topic: int | None = None
        if kind == "ready":
            if state.get("notified"):
                # Already-acknowledged work is never repeated (#3477).
                return True
            known_topic = state.get("topic_id")
            if known_topic is None and not self._claim_stale(state):
                logger.info(
                    "Lead notification already in progress: request_id=%s user=%s",
                    request_id,
                    client_id,
                )
                return False
        claimed = await self._claim_notify(
            client_id,
            request_id,
            topic_id=known_topic,
            takeover=kind != "absent",
        )
        if not claimed:
            logger.info(
                "Concurrent lead notification claim lost: request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        display_name = str(record.get("display_name") or "")
        username = str(record.get("username") or "")
        if known_topic is None:
            try:
                known_topic = await bridge.create_topic(
                    client_name=display_name or f"user {username or 'unknown'}",
                    goal="Заявка",
                )
            except Exception:
                logger.warning(
                    "Lead request topic creation failed: request_id=%s user=%s",
                    request_id,
                    client_id,
                )
                return False
            # Record the topic before sending so a failed send can resume it.
            if not await self._write_notify_state(
                client_id, request_id, status="sending", topic_id=known_topic
            ):
                logger.warning(
                    "Lead request topic created but not recorded durably; a "
                    "retry may create another (ambiguous outcome): "
                    "request_id=%s user=%s",
                    request_id,
                    client_id,
                )
                return False
        try:
            sent = await bridge.send_to_topic(
                topic_id=known_topic,
                text=_render_notification(record),
            )
        except Exception:
            logger.warning(
                "Lead request notification send failed: request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        if not sent:
            logger.warning(
                "Lead request topic vanished before notification: request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        if not await self._write_notify_state(
            client_id, request_id, status="notified", topic_id=known_topic
        ):
            logger.warning(
                "Lead notification delivered but acknowledgement not recorded; "
                "a retry may repeat it (ambiguous outcome): request_id=%s user=%s",
                request_id,
                client_id,
            )
            return False
        return True
