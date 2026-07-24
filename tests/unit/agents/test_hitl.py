"""Tests for HITL (Human-in-the-Loop) guard and preview (#443)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# --- format_hitl_preview ---


def test_format_hitl_preview_create_lead():
    """format_hitl_preview formats crm_create_lead args correctly."""
    from telegram_bot.agents.hitl import format_hitl_preview

    preview = format_hitl_preview("crm_create_lead", {"name": "Test Deal", "budget": 50000})
    assert "Создать сделку" in preview
    assert "name: Test Deal" in preview
    assert "budget: 50000" in preview


def test_format_hitl_preview_update_lead():
    """format_hitl_preview formats crm_update_lead args correctly."""
    from telegram_bot.agents.hitl import format_hitl_preview

    preview = format_hitl_preview("crm_update_lead", {"deal_id": 1, "name": "New Name"})
    assert "Обновить сделку" in preview
    assert "deal_id: 1" in preview
    assert "name: New Name" in preview


def test_format_hitl_preview_upsert_contact():
    """format_hitl_preview formats crm_upsert_contact correctly."""
    from telegram_bot.agents.hitl import format_hitl_preview

    preview = format_hitl_preview(
        "crm_upsert_contact", {"phone": "+380991234567", "first_name": "Ivan"}
    )
    assert "Создать/обновить контакт" in preview
    assert "phone: +380991234567" in preview


def test_format_hitl_preview_update_contact():
    """format_hitl_preview formats crm_update_contact correctly."""
    from telegram_bot.agents.hitl import format_hitl_preview

    preview = format_hitl_preview(
        "crm_update_contact", {"contact_id": 123, "phone": "+380991234567"}
    )
    assert "Обновить контакт" in preview
    assert "contact_id: 123" in preview


def test_format_hitl_preview_skips_none_values():
    """format_hitl_preview skips args with None values."""
    from telegram_bot.agents.hitl import format_hitl_preview

    preview = format_hitl_preview("crm_create_lead", {"name": "Deal", "budget": None})
    assert "budget" not in preview


def test_format_hitl_preview_skips_config_key():
    """format_hitl_preview skips the 'config' key."""
    from telegram_bot.agents.hitl import format_hitl_preview

    config_mock = MagicMock()
    preview = format_hitl_preview("crm_create_lead", {"name": "Deal", "config": config_mock})
    assert "config" not in preview


def test_format_hitl_preview_unknown_tool():
    """format_hitl_preview uses tool name as label for unknown tools."""
    from telegram_bot.agents.hitl import format_hitl_preview

    preview = format_hitl_preview("some_unknown_tool", {"key": "val"})
    assert "some_unknown_tool" in preview


# --- hitl_guard calls interrupt ---


def test_hitl_guard_calls_interrupt_with_payload():
    """hitl_guard calls interrupt() with structured payload."""
    from telegram_bot.agents.hitl import hitl_guard

    with patch("telegram_bot.agents.hitl.interrupt") as mock_interrupt:
        mock_interrupt.return_value = {"action": "approve"}
        result = hitl_guard(
            "crm_create_lead",
            "Создать сделку:\n  name: Test",
            {"name": "Test"},
        )
        mock_interrupt.assert_called_once_with(
            {
                "tool": "crm_create_lead",
                "preview": "Создать сделку:\n  name: Test",
                "args": {"name": "Test"},
            }
        )
        assert result == {"action": "approve"}


def test_hitl_guard_returns_cancel():
    """hitl_guard returns cancel response when user clicks cancel."""
    from telegram_bot.agents.hitl import hitl_guard

    with patch("telegram_bot.agents.hitl.interrupt", return_value={"action": "cancel"}):
        result = hitl_guard("crm_create_lead", "preview", {})
        assert result == {"action": "cancel"}


# --- pending resume trace-id store (#2224) ---


def _clear_pending_store() -> None:
    from telegram_bot.agents import hitl

    hitl._PENDING_RESUME_TRACE_IDS.clear()


def test_pending_resume_trace_id_roundtrip():
    """set then pop returns the stored parent trace id for a thread."""
    from telegram_bot.agents.hitl import (
        pop_pending_resume_trace_id,
        set_pending_resume_trace_id,
    )

    _clear_pending_store()
    set_pending_resume_trace_id("tg_42", "trace-abc")
    assert pop_pending_resume_trace_id("tg_42") == "trace-abc"


def test_pending_resume_trace_id_pop_is_one_shot():
    """A second pop returns None — the entry is cleared on first read."""
    from telegram_bot.agents.hitl import (
        pop_pending_resume_trace_id,
        set_pending_resume_trace_id,
    )

    _clear_pending_store()
    set_pending_resume_trace_id("tg_42", "trace-abc")
    assert pop_pending_resume_trace_id("tg_42") == "trace-abc"
    assert pop_pending_resume_trace_id("tg_42") is None


def test_pending_resume_trace_id_missing_returns_none():
    from telegram_bot.agents.hitl import pop_pending_resume_trace_id

    _clear_pending_store()
    assert pop_pending_resume_trace_id("tg_does_not_exist") is None


def test_pending_resume_trace_id_ignores_empty_inputs():
    """Empty thread_id or trace_id must not create an entry."""
    from telegram_bot.agents.hitl import (
        pop_pending_resume_trace_id,
        set_pending_resume_trace_id,
    )

    _clear_pending_store()
    set_pending_resume_trace_id("", "trace-abc")
    set_pending_resume_trace_id("tg_42", None)
    set_pending_resume_trace_id("tg_42", "")
    assert pop_pending_resume_trace_id("tg_42") is None


def test_pending_resume_trace_id_store_is_bounded():
    """The store evicts oldest entries past its cap (no unbounded growth)."""
    from cachetools import LRUCache

    from telegram_bot.agents import hitl
    from telegram_bot.agents.hitl import (
        pop_pending_resume_trace_id,
        set_pending_resume_trace_id,
    )

    _clear_pending_store()
    with patch.object(hitl, "_PENDING_RESUME_TRACE_IDS", LRUCache(maxsize=3)):
        for i in range(5):
            set_pending_resume_trace_id(f"tg_{i}", f"trace-{i}")
        # Oldest two (tg_0, tg_1) evicted; newest three retained.
        assert pop_pending_resume_trace_id("tg_0") is None
        assert pop_pending_resume_trace_id("tg_1") is None
        assert pop_pending_resume_trace_id("tg_4") == "trace-4"
    _clear_pending_store()
