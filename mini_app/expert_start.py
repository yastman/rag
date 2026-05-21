"""Start expert conversation — creates forum topic + sends first message."""

from __future__ import annotations

from pydantic import BaseModel


class StartExpertRequest(BaseModel):
    """Request body for ``POST /api/start-expert``.

    ``user_id`` is optional (and ignored) at the body level: the API
    derives the authoritative Telegram user id from the SDK-validated
    initData header (#1595). Any body value is accepted for backward
    compatibility but is overwritten server-side.
    """

    expert_id: str
    user_id: int | None = None
    message: str | None = None
    query_id: str | None = None


class StartExpertResponse(BaseModel):
    start_link: str
    expert_name: str
    status: str = "ok"
