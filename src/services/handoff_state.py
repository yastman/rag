"""Redis-backed state machine for manager handoff.

Keys:
    handoff:{client_id}  — hash with HandoffData fields
    topic_map:{topic_id} — string → client_id (reverse lookup)
"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field, TypeAdapter, field_serializer, field_validator
from redis.asyncio import Redis


logger = logging.getLogger(__name__)

_PREFIX = "handoff"
_TOPIC_PREFIX = "topic_map"
_QUALIFICATION_ADAPTER = TypeAdapter(dict[str, str])


class HandoffData(BaseModel):
    """State for an active handoff session."""

    client_id: int
    topic_id: int
    mode: str = "human_waiting"  # bot | human_waiting | human
    lead_id: int | None = None
    created_at: float = Field(default_factory=time.time)
    manager_joined_at: float | None = None
    qualification: dict[str, str] = Field(default_factory=dict)

    @field_validator("lead_id", "manager_joined_at", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("qualification", mode="before")
    @classmethod
    def _parse_qualification(cls, value: object) -> object:
        if value in (None, ""):
            return {}
        if isinstance(value, str):
            return _QUALIFICATION_ADAPTER.validate_json(value)
        return value

    @field_serializer("qualification", when_used="json")
    def _serialize_qualification(self, value: dict[str, str]) -> str:
        return _QUALIFICATION_ADAPTER.dump_json(value).decode()

    def to_redis_dict(self) -> dict[str, str]:
        payload = self.model_dump(mode="json")
        return {k: "" if v is None else str(v) for k, v in payload.items()}

    @classmethod
    def from_redis_dict(cls, raw: dict[str, str]) -> HandoffData:
        return cls.model_validate(raw)


class HandoffState:
    """Manage handoff state in Redis."""

    def __init__(self, redis: Redis, *, ttl_hours: int = 72) -> None:
        self._redis = redis
        self._ttl = ttl_hours * 3600

    async def set(self, data: HandoffData) -> None:
        key = f"{_PREFIX}:{data.client_id}"
        rev_key = f"{_TOPIC_PREFIX}:{data.topic_id}"
        current = await self.get_by_client(data.client_id)
        pipe = self._redis.pipeline()
        if current is not None and current.topic_id != data.topic_id:
            # Topic replace (#3487): drop the old reverse key in the same batch
            # so the old topic never resolves to the new session. Skip the
            # delete when another client has taken the old topic over.
            stale_rev_key = f"{_TOPIC_PREFIX}:{current.topic_id}"
            mapped = await self._redis.get(stale_rev_key)
            if mapped is None or int(mapped) == data.client_id:
                pipe.delete(stale_rev_key)
        pipe.hset(key, mapping=data.to_redis_dict())
        pipe.expire(key, self._ttl)
        pipe.set(rev_key, str(data.client_id), ex=self._ttl)
        await pipe.execute()

    async def get_by_client(self, client_id: int) -> HandoffData | None:
        raw = await self._redis.hgetall(f"{_PREFIX}:{client_id}")  # type: ignore[misc]
        if not raw:
            return None
        return HandoffData.from_redis_dict(raw)

    async def get_by_topic(self, topic_id: int) -> HandoffData | None:
        client_id = await self._redis.get(f"{_TOPIC_PREFIX}:{topic_id}")
        if not client_id:
            return None
        data = await self.get_by_client(int(client_id))
        if data is None or data.topic_id != topic_id:
            # Stale/garbage reverse key: the client's current session lives in
            # another topic, so this topic must not resolve to it (#3487).
            return None
        return data

    async def update_mode(self, client_id: int, mode: str) -> None:
        data = await self.get_by_client(client_id)
        if not data:
            return
        data.mode = mode
        if mode == "human":
            data.manager_joined_at = time.time()
        await self.set(data)

    async def delete(self, client_id: int, *, expected_topic_id: int | None = None) -> bool:
        """Remove a session plus its reverse mapping; return whether it was removed.

        With ``expected_topic_id`` the delete acts as a guarded snapshot close
        (#3487): when the client's current session has moved to a different
        topic, the newer session is preserved untouched and ``False`` is
        returned instead of destroying it.
        """
        data = await self.get_by_client(client_id)
        if not data:
            return False
        if expected_topic_id is not None and data.topic_id != expected_topic_id:
            logger.info(
                "Handoff delete skipped: client %s moved from topic %s to %s (#3487)",
                client_id,
                expected_topic_id,
                data.topic_id,
            )
            return False
        pipe = self._redis.pipeline()
        pipe.delete(f"{_PREFIX}:{client_id}")
        pipe.delete(f"{_TOPIC_PREFIX}:{data.topic_id}")
        await pipe.execute()
        return True
