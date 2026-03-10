"""Start expert conversation — creates forum topic + sends first message."""

from __future__ import annotations

from pydantic import BaseModel


class StartExpertRequest(BaseModel):
    user_id: int
    expert_id: str
    message: str | None = None
    query_id: str | None = None


class StartExpertResponse(BaseModel):
    start_link: str
    expert_name: str
    status: str = "ok"
