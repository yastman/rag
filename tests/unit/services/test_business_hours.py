from datetime import UTC, datetime

import pytest

from telegram_bot.services.util.business_hours import is_business_hours


# Windows CI/dev often lacks the system tzdb and the optional ``tzdata`` wheel.
# Business-hours logic only needs weekday + hour, so pin ZoneInfo to a fixed
# UTC tzinfo and exercise the contract without IANA zone files.
_UTC = UTC


@pytest.fixture(autouse=True)
def _fixed_zoneinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "telegram_bot.services.util.business_hours.ZoneInfo",
        lambda _key: _UTC,
    )


def test_during_business_hours():
    # Wednesday 10:30
    dt = datetime(2026, 3, 4, 10, 30, tzinfo=_UTC)
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is True


def test_before_business_hours():
    dt = datetime(2026, 3, 4, 7, 0, tzinfo=_UTC)
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False


def test_after_business_hours():
    dt = datetime(2026, 3, 4, 20, 0, tzinfo=_UTC)
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False


def test_weekend():
    # Saturday 12:00 — still outside business hours (weekday only)
    dt = datetime(2026, 3, 7, 12, 0, tzinfo=_UTC)
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False


def test_boundary_start():
    dt = datetime(2026, 3, 4, 9, 0, tzinfo=_UTC)
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is True


def test_boundary_end():
    dt = datetime(2026, 3, 4, 18, 0, tzinfo=_UTC)
    assert is_business_hours(dt, start=9, end=18, tz="Europe/Sofia") is False
