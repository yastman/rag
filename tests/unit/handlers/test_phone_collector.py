# tests/unit/handlers/test_phone_collector.py
"""Tests for phone collection flow."""

from telegram_bot.handlers.phone_collector import (
    PhoneCollectorStates,
    create_phone_router,
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


def test_create_phone_router_returns_fresh_instance():
    """Router factory must return a new instance for each bot/dispatcher."""
    router_a = create_phone_router()
    router_b = create_phone_router()

    assert router_a is not router_b
    assert router_a.name == "phone_collector"
    assert router_b.name == "phone_collector"
