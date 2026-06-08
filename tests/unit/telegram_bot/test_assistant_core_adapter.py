"""Tests for Telegram assistant-core adapter helpers."""

from __future__ import annotations


def test_build_user_context_is_transport_neutral() -> None:
    from telegram_bot.assistant_core_adapter import build_user_context

    ctx = build_user_context(
        user_id=42,
        session_id="s-1",
        role="manager",
        filters={"city": "Sofia"},
    )

    assert ctx.user_id == "42"
    assert ctx.session_id == "s-1"
    assert ctx.role == "manager"
    assert ctx.filters == {"city": "Sofia"}
    assert ctx.language == "ru"


def test_core_entrypoint_flag_defaults_off(monkeypatch) -> None:
    from telegram_bot.assistant_core_adapter import (
        CORE_ENTRYPOINT_ENV,
        core_entrypoint_enabled,
    )

    monkeypatch.delenv(CORE_ENTRYPOINT_ENV, raising=False)

    assert not core_entrypoint_enabled()


def test_response_text_for_telegram_returns_core_text() -> None:
    from src.core import AssistantResult
    from telegram_bot.assistant_core_adapter import response_text_for_telegram

    assert response_text_for_telegram(AssistantResult(response_text="hello")) == "hello"
