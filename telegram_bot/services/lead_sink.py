"""Durable lead-request sink for phone-collected requests (#3213).

The phone collector (#628) used to confirm "заявка оформлена" without any
durable write or manager notification. This module is the observable sink
behind that confirmation:

- **Persistence** — each request is written to the Redis hash
  ``lead_request:{client_id}`` with a TTL.
- **Manager notification** — when the Forum Topics bridge is configured,
  a dedicated topic is created in the managers group and the request
  details (including the phone number managers need to call back) are
  posted there.

``record_request`` returns ``True`` only when persistence is acknowledged
and, if the notification channel is configured, the notification is also
acknowledged. Callers must gate success copy on that acknowledgement:
never confirm a request that no sink observed (#3213).

Privacy: raw phone values are never written to application logs — they
exist only in the durable record and the manager notification.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import TypeAdapter

from telegram_bot.services.forum_bridge import ForumBridge


logger = logging.getLogger(__name__)

_PREFIX = "lead_request"
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
        phone: str,
        service_key: str,
        username: str | None = None,
        display_name: str = "",
        viewing_objects: list[dict[str, Any]] | None = None,
        date_range: str | None = None,
    ) -> bool:
        """Record a request. Returns True only after acknowledged sink writes.

        Persistence (Redis) is attempted first; if the Forum Topics bridge is
        configured, its notification must also be acknowledged before this
        method reports success.
        """
        objects = viewing_objects or []
        persisted = await self._persist(
            client_id=client_id,
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

    async def _persist(
        self,
        *,
        client_id: int,
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
            "phone": phone,
            "service_key": service_key,
            "username": username or "",
            "display_name": display_name,
            "viewing_objects": _OBJECTS_ADAPTER.dump_json(viewing_objects).decode(),
            "date_range": date_range or "",
            "created_at": str(int(time.time())),
        }
        key = f"{_PREFIX}:{client_id}"
        try:
            pipe = self._redis.pipeline()
            pipe.hset(key, mapping=record)
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
