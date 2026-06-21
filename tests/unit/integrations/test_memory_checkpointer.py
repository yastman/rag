"""Tests for create_redis_checkpointer honest no-op behavior (#2944)."""

import logging

import pytest

from telegram_bot.integrations.memory import create_redis_checkpointer


def test_create_redis_checkpointer_raises_not_implemented() -> None:
    """create_redis_checkpointer must raise NotImplementedError, not silently return MemorySaver.

    After LangGraph removal (#2843) the AsyncRedisSaver SDK is not installed.
    Returning a MemorySaver while logging 'Creating AsyncRedisSaver' is a
    silent no-op that hides the fact that Redis persistence is disabled (#2944).
    """
    with pytest.raises(NotImplementedError):
        create_redis_checkpointer("redis://localhost:6379")


def test_create_redis_checkpointer_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """The raised error path must log a WARNING, not an INFO 'success' message."""
    with caplog.at_level(logging.WARNING, logger="telegram_bot.integrations.memory"):
        with pytest.raises(NotImplementedError):
            create_redis_checkpointer("redis://localhost:6379")

    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(
        "disabled" in m.lower() or "not implemented" in m.lower() or "removed" in m.lower()
        for m in warning_messages
    ), f"Expected a warning about disabled/removed checkpointer, got: {warning_messages}"
