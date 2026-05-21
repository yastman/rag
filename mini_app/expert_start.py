"""Start expert conversation — creates forum topic + sends first message."""

from __future__ import annotations

from pydantic import BaseModel


class StartExpertRequest(BaseModel):
    expert_id: str
    message: str | None = None
    query_id: str | None = None
    # user_id is accepted from the body for backward compat but is always
    # overridden by the server-verified value from Telegram initData (#1595).
    user_id: int | None = None


class StartExpertResponse(BaseModel):
    start_link: str
    expert_name: str
    status: str = "ok"
