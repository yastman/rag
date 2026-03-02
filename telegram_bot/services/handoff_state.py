"""Redis-backed state machine for manager handoff.

Keys:
    handoff:{client_id}  — hash with HandoffData fields
    topic_map:{topic_id} — string → client_id (reverse lookup)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from redis.asyncio import Redis


logger = logging.getLogger(__name__)

_PREFIX = "handoff"
_TOPIC_PREFIX = "topic_map"


@dataclass
class HandoffData:
    """State for an active handoff session."""

    client_id: int
    topic_id: int
    mode: str = "human_waiting"  # bot | human_waiting | human
    lead_id: int | None = None
    created_at: float = field(default_factory=time.time)
    manager_joined_at: float | None = None
    qualification: dict[str, str] = field(default_factory=dict)

    def to_redis_dict(self) -> dict[str, str]:
        return {
            "client_id": str(self.client_id),
            "topic_id": str(self.topic_id),
            "mode": self.mode,
            "lead_id": str(self.lead_id) if self.lead_id else "",
            "created_at": str(self.created_at),
            "manager_joined_at": str(self.manager_joined_at) if self.manager_joined_at else "",
            "qualification": json.dumps(self.qualification, ensure_ascii=False),
        }

    @classmethod
    def from_redis_dict(cls, raw: dict[str, str]) -> HandoffData:
        return cls(
            client_id=int(raw["client_id"]),
            topic_id=int(raw["topic_id"]),
            mode=raw.get("mode", "human_waiting"),
            lead_id=int(raw["lead_id"]) if raw.get("lead_id") else None,
            created_at=float(raw.get("created_at", 0)),
            manager_joined_at=(
                float(raw["manager_joined_at"]) if raw.get("manager_joined_at") else None
            ),
            qualification=json.loads(raw.get("qualification", "{}")),
        )


class HandoffState:
    """Manage handoff state in Redis."""

    def __init__(self, redis: Redis, *, ttl_hours: int = 24) -> None:
        self._redis = redis
        self._ttl = ttl_hours * 3600

    async def set(self, data: HandoffData) -> None:
        key = f"{_PREFIX}:{data.client_id}"
        rev_key = f"{_TOPIC_PREFIX}:{data.topic_id}"
        pipe = self._redis.pipeline()
        pipe.hset(key, mapping=data.to_redis_dict())
        pipe.expire(key, self._ttl)
        pipe.set(rev_key, str(data.client_id), ex=self._ttl)
        await pipe.execute()

    async def get_by_client(self, client_id: int) -> HandoffData | None:
        raw = await self._redis.hgetall(f"{_PREFIX}:{client_id}")
        if not raw:
            return None
        return HandoffData.from_redis_dict(raw)

    async def get_by_topic(self, topic_id: int) -> HandoffData | None:
        client_id = await self._redis.get(f"{_TOPIC_PREFIX}:{topic_id}")
        if not client_id:
            return None
        return await self.get_by_client(int(client_id))

    async def update_mode(self, client_id: int, mode: str) -> None:
        key = f"{_PREFIX}:{client_id}"
        updates: dict[str, str] = {"mode": mode}
        if mode == "human":
            updates["manager_joined_at"] = str(time.time())
        await self._redis.hset(key, mapping=updates)

    async def delete(self, client_id: int) -> None:
        data = await self.get_by_client(client_id)
        if not data:
            return
        pipe = self._redis.pipeline()
        pipe.delete(f"{_PREFIX}:{client_id}")
        pipe.delete(f"{_TOPIC_PREFIX}:{data.topic_id}")
        await pipe.execute()
