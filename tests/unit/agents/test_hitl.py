"""Tests for HITL (Human-in-the-Loop) guard and preview (#443)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.runnables import RunnableConfig

from telegram_bot.agents.context import BotContext


def _make_config(bot_context: BotContext) -> RunnableConfig:
    return RunnableConfig(configurable={"bot_context": bot_context})


def _make_ctx(mock_kommo) -> BotContext:
    return BotContext(
        telegram_user_id=42,
        session_id="s-1",
        language="ru",
        kommo_client=mock_kommo,
        history_service=AsyncMock(),
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
    )


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


# --- HITL-wrapped CRM tools ---


async def test_crm_create_lead_approve():
    """crm_create_lead executes after approve."""
    from telegram_bot.agents.crm_tools import crm_create_lead
    from telegram_bot.services.kommo_models import Lead

    mock_kommo = AsyncMock()
    mock_kommo.create_lead = AsyncMock(return_value=Lead(id=2, name="Test Deal"))
    ctx = _make_ctx(mock_kommo)

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_create_lead.ainvoke(
            {"name": "Test Deal", "budget": 50000},
            config=_make_config(ctx),
        )
    assert "Сделка создана" in result
    mock_kommo.create_lead.assert_called_once()


async def test_crm_create_lead_cancel():
    """crm_create_lead returns cancel message when action != approve."""
    from telegram_bot.agents.crm_tools import crm_create_lead
    from telegram_bot.services.kommo_models import Lead

    mock_kommo = AsyncMock()
    mock_kommo.create_lead = AsyncMock(return_value=Lead(id=2, name="Test"))
    ctx = _make_ctx(mock_kommo)

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "cancel"}):
        result = await crm_create_lead.ainvoke(
            {"name": "Test Deal"},
            config=_make_config(ctx),
        )
    assert "Операция отменена" in result
    mock_kommo.create_lead.assert_not_called()


async def test_crm_update_lead_approve():
    """crm_update_lead executes after approve."""
    from telegram_bot.agents.crm_tools import crm_update_lead
    from telegram_bot.services.kommo_models import Lead

    mock_kommo = AsyncMock()
    mock_kommo.update_lead = AsyncMock(return_value=Lead(id=1, name="Updated"))
    ctx = _make_ctx(mock_kommo)

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_update_lead.ainvoke(
            {"deal_id": 1, "name": "Updated"},
            config=_make_config(ctx),
        )
    assert "обновлена" in result.lower()
    mock_kommo.update_lead.assert_called_once()


async def test_crm_upsert_contact_cancel():
    """crm_upsert_contact returns cancel message when action != approve."""
    from telegram_bot.agents.crm_tools import crm_upsert_contact

    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact = AsyncMock()
    ctx = _make_ctx(mock_kommo)

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "cancel"}):
        result = await crm_upsert_contact.ainvoke(
            {"phone": "+380991234567", "first_name": "Ivan"},
            config=_make_config(ctx),
        )
    assert "Операция отменена" in result
    mock_kommo.upsert_contact.assert_not_called()


async def test_crm_update_contact_approve():
    """crm_update_contact executes after approve."""
    from telegram_bot.agents.crm_tools import crm_update_contact
    from telegram_bot.services.kommo_models import Contact

    mock_kommo = AsyncMock()
    mock_kommo.update_contact = AsyncMock(return_value=Contact(id=50, first_name="Updated"))
    ctx = _make_ctx(mock_kommo)

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_update_contact.ainvoke(
            {"contact_id": 50, "phone": "+380991234567"},
            config=_make_config(ctx),
        )
    assert "Контакт обновлен" in result
    mock_kommo.update_contact.assert_called_once()


async def test_crm_update_contact_cancel():
    """crm_update_contact returns cancel message when action != approve."""
    from telegram_bot.agents.crm_tools import crm_update_contact

    mock_kommo = AsyncMock()
    mock_kommo.update_contact = AsyncMock()
    ctx = _make_ctx(mock_kommo)

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "cancel"}):
        result = await crm_update_contact.ainvoke(
            {"contact_id": 50, "phone": "+380991234567"},
            config=_make_config(ctx),
        )
    assert "Операция отменена" in result
    mock_kommo.update_contact.assert_not_called()
