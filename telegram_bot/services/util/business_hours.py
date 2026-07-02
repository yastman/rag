"""Business hours checker for handoff flow."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def is_business_hours(
    dt: datetime | None = None,
    *,
    start: int = 9,
    end: int = 18,
    tz: str = "Europe/Sofia",
) -> bool:
    if dt is None:
        dt = datetime.now(ZoneInfo(tz))
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    local = dt.astimezone(ZoneInfo(tz))
    # Weekdays only (Mon=0, Sun=6).
    if local.weekday() >= 5:
        return False
    return start <= local.hour < end
