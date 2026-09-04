"""Durable lead-request sink for phone-collected requests (#3213, #3322).

The phone collector (#628) used to confirm "заявка оформлена" without any
durable write or manager notification. This module is the observable sink
behind that confirmation:

- **Persistence** — each request is written to the versioned Redis hash
  ``lead_request:v2:{client_id}`` with the caller-provided ``request_id`` as
  the hash field and a TTL. Distinct requests coexist as distinct fields and
  a retry of the same ``request_id`` is a no-op (HSETNX), so the first
  acknowledgement is the record (#3322).
- **Manager notification** — when the Forum Topics bridge is configured,
  a dedicated topic is created in the managers group and the request
  details (including the phone number managers need to call back) are
  posted there.

Legacy compatibility (#3322): the pre-v2 sink overwrote the single hash
``lead_request:{client_id}`` per client. During the compatibility window
that key is never written, rewritten, or deleted by this module;
:meth:`LeadRequestSink.list_requests` merges its contents into the v2
listing read-only. The v2 namespace lives under a different key, so a
pre-v2 reader observing ``lead_request:{client_id}`` never sees v2 records.

``record_request`` returns ``True`` only when persistence is acknowledged
and, if the notification channel is configured, the notification is also
acknowledged. Callers must gate success copy on that acknowledgement:
never confirm a request that no sink observed (#3213).

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
_OBJECTS_ADAPTER = TypeAdapter(list[dict[str, Any]])

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

        Persistence (Redis) is attempted first; if the Forum Topics bridge is
        configured, its notification must also be acknowledged before this
        method reports success.
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
        if self._forum_bridge is not None:
            notified = await self._notify(
                phone=phone,
                service_key=service_key,
                username=username,
                display_name=display_name,
                viewing_objects=objects,
                date_range=date_range,
            )
            if not notified:
                if persisted:
                    logger.info(
                        "Lead request persisted but manager notification failed: "
                        "service_key=%s user=%s",
                        service_key,
                        client_id,
                    )
                return False
        return persisted

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

    async def _notify(
        self,
        *,
        phone: str,
        service_key: str,
        username: str | None,
        display_name: str,
        viewing_objects: list[dict[str, Any]],
        date_range: str | None,
    ) -> bool:
        bridge = self._forum_bridge
        if bridge is None:
            return False
        try:
            topic_id = await bridge.create_topic(
                client_name=display_name or f"user {username or 'unknown'}",
                goal="Заявка",
            )
            lines = ["--- Новая заявка ---"]
            lines.append(f"Телефон: {phone}")
            lines.append(f"Тип: {service_key}")
            if username:
                lines.append(f"Telegram: @{username}")
            when = _date_label(date_range)
            if when:
                lines.append(f"Когда: {when}")
            object_lines = _format_objects(viewing_objects)
            if object_lines:
                lines.append("Объекты:")
                lines.extend(object_lines)
            lines.append("---")
            sent = await bridge.send_to_topic(topic_id=topic_id, text="\n".join(lines))
        except Exception:
            logger.warning(
                "Lead request manager notification failed: service_key=%s",
                service_key,
            )
            return False
        if not sent:
            logger.warning(
                "Lead request topic vanished before notification: service_key=%s",
                service_key,
            )
            return False
        return True
