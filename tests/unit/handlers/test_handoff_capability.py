"""Capability gate for the Forum manager handoff (#3239).

The interactive handoff (qualification dialog → forum topic → relay →
``/close``) starts only when ``HANDOFF_ENABLED`` is set AND the Forum
bridge AND the Redis handoff state exist. Otherwise manager actions fall
back to the durable phone-request sink (#3213), and bridge failures
produce explicit failure copy — never a promise of future manager
contact.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from telegram_bot.handlers import bot_handoff
from tests.unit._bot_config_factory import make_bot_config

_FALSE_PROMISE_MARKERS = ("скоро свяжется", "менеджер скоро")


def _capability_bot(
    *,
    handoff_enabled: bool = False,
    bridge: object = None,
    handoff_state: object = None,
):
    """Partially constructed PropertyBot with just the handoff attributes."""
    from telegram_bot.bot import PropertyBot

    bot = PropertyBot.__new__(PropertyBot)
    bot.config = make_bot_config(handoff_enabled=handoff_enabled, managers_group_id=-100123)
    bot._forum_bridge = bridge
    bot._handoff_state = handoff_state
    return bot


def _message():
    message = MagicMock()
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()
    return message


def _state():
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    return state


# --- forum_handoff_available -------------------------------------------------


def test_capability_requires_all_three_conditions():
    bridge = MagicMock()
    state = MagicMock()

    off = _capability_bot(handoff_enabled=False, bridge=bridge, handoff_state=state)
    assert off.forum_handoff_available is False

    no_state = _capability_bot(handoff_enabled=True, bridge=bridge, handoff_state=None)
    assert no_state.forum_handoff_available is False

    no_bridge = _capability_bot(handoff_enabled=True, bridge=None, handoff_state=state)
    assert no_bridge.forum_handoff_available is False

    full = _capability_bot(handoff_enabled=True, bridge=bridge, handoff_state=state)
    assert full.forum_handoff_available is True


# --- _handle_manager gating ---------------------------------------------------


@pytest.mark.asyncio
async def test_handle_manager_capability_on_starts_qualification():
    bot = _capability_bot(
        handoff_enabled=True, bridge=MagicMock(), handoff_state=MagicMock()
    )
    message = _message()
    state = _state()

    with patch.object(
        bot_handoff, "start_qualification", new_callable=AsyncMock
    ) as mock_qual:
        await bot_handoff._handle_manager(bot, message, state=state)

    mock_qual.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_manager_bridge_without_handoff_enabled_routes_to_phone():
    """A bridge alone must NOT start the forum handoff (#3239)."""
    bot = _capability_bot(handoff_enabled=False, bridge=MagicMock(), handoff_state=MagicMock())
    message = _message()
    state = _state()

    with (
        patch.object(bot_handoff, "start_qualification", new_callable=AsyncMock) as mock_qual,
        patch(
            "telegram_bot.handlers.phone_collector.start_phone_collection",
            new_callable=AsyncMock,
        ) as mock_phone,
    ):
        await bot_handoff._handle_manager(bot, message, state=state)

    mock_qual.assert_not_awaited()
    mock_phone.assert_awaited_once()
    assert mock_phone.await_args.kwargs["service_key"] == "manager"


@pytest.mark.asyncio
async def test_handle_manager_without_capability_or_state_answers_without_agent_dispatch():
    """No capability + no FSM — truthful copy, no 'Соедини с менеджером' agent dispatch."""
    bot = _capability_bot(handoff_enabled=False, bridge=None, handoff_state=None)
    bot.handle_menu_action_text = AsyncMock()
    message = _message()

    await bot_handoff._handle_manager(bot, message, state=None)

    bot.handle_menu_action_text.assert_not_awaited()
    sent = message.answer.await_args.args[0]
    assert "менеджер" in sent.lower()
    for marker in _FALSE_PROMISE_MARKERS:
        assert marker not in sent


# --- _complete_handoff failure explicitness -----------------------------------


def _completion_bot(bridge):
    """Bot attributes needed by _complete_handoff after the entry-point gate."""
    from telegram_bot.bot import PropertyBot

    bot = PropertyBot.__new__(PropertyBot)
    bot.config = SimpleNamespace(
        handoff_summary_min_messages=3,
        business_hours_start=9,
        business_hours_end=18,
        business_hours_tz="Europe/Sofia",
    )
    bot._forum_bridge = bridge
    bot._handoff_state = None
    cache = MagicMock()
    cache.redis = None
    bot._cache = cache
    return bot


@pytest.mark.asyncio
async def test_complete_handoff_topic_creation_failure_shows_no_promise():
    """Failed topic creation → explicit failure copy, FSM untouched (#3239)."""
    bridge = MagicMock()
    bridge.create_topic = AsyncMock(
        side_effect=TelegramBadRequest(method=None, message="no rights")
    )
    bot = _completion_bot(bridge)
    message = _message()
    state = _state()

    await bot_handoff._complete_handoff(
        bot,
        user_id=1,
        username="u",
        display_name="User",
        locale="ru",
        qualification={"goal": "consult"},
        message=message,
        state=state,
    )

    state.set_state.assert_not_awaited()
    for send in (message.edit_text, message.answer):
        for call in send.await_args_list:
            text = call.args[0] if call.args else ""
            for marker in _FALSE_PROMISE_MARKERS:
                assert marker not in text, f"false promise shown: {text!r}"
    failure_shown = any(
        "не был" in (call.args[0] if call.args else "")
        for call in message.edit_text.await_args_list
    )
    assert failure_shown, "explicit failure copy was not shown"


@pytest.mark.asyncio
async def test_complete_handoff_without_bridge_reports_failure_instead_of_silence():
    """Bridge missing at completion time → explicit failure copy, not a silent return."""
    bot = _completion_bot(None)
    message = _message()

    await bot_handoff._complete_handoff(
        bot,
        user_id=1,
        username="u",
        display_name="User",
        locale="ru",
        qualification={"goal": "consult"},
        message=message,
        state=None,
    )

    failure_shown = any(
        "не был" in (call.args[0] if call.args else "")
        for call in message.edit_text.await_args_list
    )
    assert failure_shown, "explicit failure copy was not shown"


# --- lifecycle wiring log keeps the #3213 sink independent ---------------------


def test_setup_handoff_services_keeps_sink_without_handoff_enabled():
    """The #3213 lead sink must keep its bridge notification independent of
    the interactive handoff capability (#3239)."""
    from telegram_bot.lifecycle.lifecycle import setup_handoff_services
    from telegram_bot.services.lead_sink import LeadRequestSink

    bot = MagicMock()
    bot._cache = MagicMock(redis=object())
    bot.config.managers_group_id = -100123
    bot.config.handoff_enabled = False

    setup_handoff_services(bot)

    assert isinstance(bot._lead_sink, LeadRequestSink)
    # Bridge still constructed — the sink's manager notification stays usable.
    assert bot._forum_bridge is not None
