"""User and Lead data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class User:
    """Bot user (client or manager)."""

    telegram_id: int
    id: int | None = None
    locale: str = "ru"
    role: str = "client"  # client, manager, admin
    first_name: str | None = None
    telegram_language_code: str | None = None
    notifications_enabled: bool = True


@dataclass
class Lead:
    """Sales lead with qualification data."""

    user_id: int
    id: int | None = None
    stage: str = "new"  # new, qualified, hot, warm, cold, converted
    score: int = 0
    preferences: dict = field(default_factory=dict)
    kommo_lead_id: int | None = None
