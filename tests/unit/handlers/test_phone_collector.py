# tests/unit/handlers/test_phone_collector.py
"""Tests for phone collection flow."""

from telegram_bot.handlers.phone_collector import (
    PhoneCollectorStates,
    validate_phone,
)


def test_validate_phone_valid():
    assert validate_phone("+380501234567") is True
    assert validate_phone("+359896759292") is True
    assert validate_phone("0501234567") is True


def test_validate_phone_invalid():
    assert validate_phone("hello") is False
    assert validate_phone("") is False
    assert validate_phone("123") is False


def test_states_defined():
    assert hasattr(PhoneCollectorStates, "waiting_phone")
