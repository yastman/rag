from datetime import datetime
from zoneinfo import ZoneInfo

from telegram_bot.services.business_hours import is_business_hours


def test_during_business_hours():
    # Wednesday 10:30 Sofia time
    dt = datetime(2026, 3, 4, 10, 30, tzinfo=ZoneInfo("Europe/Sofia"))
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is True


def test_before_business_hours():
    dt = datetime(2026, 3, 4, 7, 0, tzinfo=ZoneInfo("Europe/Sofia"))
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False


def test_after_business_hours():
    dt = datetime(2026, 3, 4, 20, 0, tzinfo=ZoneInfo("Europe/Sofia"))
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False


def test_weekend():
    # Saturday 12:00 — still outside business hours (weekday only)
    dt = datetime(2026, 3, 7, 12, 0, tzinfo=ZoneInfo("Europe/Sofia"))
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False


def test_boundary_start():
    dt = datetime(2026, 3, 4, 9, 0, tzinfo=ZoneInfo("Europe/Sofia"))
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is True


def test_boundary_end():
    dt = datetime(2026, 3, 4, 18, 0, tzinfo=ZoneInfo("Europe/Sofia"))
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False
