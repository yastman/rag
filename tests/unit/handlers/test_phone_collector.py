# tests/unit/handlers/test_phone_collector.py
"""Tests for phone collection flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram_bot.handlers.phone_collector import (
    PhoneCollectorStates,
    build_display_name,
    on_phone_contact,
)
from telegram_bot.keyboards.phone_keyboard import normalize_phone, validate_phone


def test_validate_phone_valid():
    assert validate_phone("+380501234567") is True
    assert validate_phone("+359896759292") is True
    # "0501234567" was accepted by the old digit-count regex (^\\+?\\d{7,15}$)
    # but is ambiguous without a country code: phonenumbers.is_valid_number
    # rejects it because national-only numbers are not E.164-resolvable for
    # the default BG region. Callers must supply an international format.
    assert validate_phone("0501234567") is False  # national-only, no country code


def test_validate_phone_invalid():
    assert validate_phone("hello") is False
    assert validate_phone("") is False
    assert validate_phone("123") is False


# --- normalize_phone tests (Task 3: phonenumbers validation) ---


def test_normalize_phone_returns_e164_for_valid_international():
    assert normalize_phone("+380501234567") == "+380501234567"
    assert normalize_phone("+359896759292") == "+359896759292"


def test_normalize_phone_returns_none_for_all_same_digits():
    """Fake numbers like 0000000000 or 1111111 must be rejected."""
    assert normalize_phone("+00000000000") is None
    assert normalize_phone("+11111111111") is None


def test_normalize_phone_returns_none_for_non_numeric():
    assert normalize_phone("hello") is None
    assert normalize_phone("") is None


def test_normalize_phone_returns_none_for_too_short():
    assert normalize_phone("+123") is None


def test_normalize_phone_normalizes_formatting():
    """Spaces and dashes are cleaned before parsing."""
    assert normalize_phone("+38 050 123-45-67") == "+380501234567"


def test_states_defined():
    assert hasattr(PhoneCollectorStates, "waiting_phone")


# --- build_display_name tests ---


def test_build_display_name_first_last():
    user = SimpleNamespace(first_name="Иван", last_name="Петров", username=None)
    assert build_display_name(user, "+380501234567") == "Иван П."


def test_build_display_name_first_only():
    user = SimpleNamespace(first_name="Иван", last_name=None, username=None)
    assert build_display_name(user, "+380501234567") == "Иван"


def test_build_display_name_username():
    user = SimpleNamespace(first_name=None, last_name=None, username="ivan")
    assert build_display_name(user, "+380501234567") == "@ivan"


def test_build_display_name_phone():
    assert build_display_name(None, "+380501234567") == "+380501234567"


import telegram_bot.handlers.phone_collector as mod


async def test_phone_error_message_shows_format_mask():
    """Fallback error message should show format examples, not raw phone numbers."""
    state = AsyncMock()
    message = AsyncMock()
    # Use a phone-like string (5+ digits) that fails validate_phone
    message.text = "+11111111111"
    message.from_user = SimpleNamespace(id=1, first_name="Test", last_name=None, username=None)

    await mod.on_phone_received(message, state)

    call_text = message.answer.call_args[0][0]
    assert "+359" in call_text
    assert "+380501234567" not in call_text


# --- Reply keyboard and contact handler tests ---


async def test_on_phone_received_non_phone_text_exits_fsm():
    """Text without 5+ digits should silently exit FSM."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "Какие есть апартаменты?"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    await mod.on_phone_received(message, state)

    state.clear.assert_awaited_once()
    assert (
        "отменён" in message.answer.call_args[0][0].lower()
        or "отменен" in message.answer.call_args[0][0].lower()
    )


async def test_on_phone_contact_valid_processes_phone():
    """on_phone_contact with valid contact records via the sink and confirms."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.contact = MagicMock()
    message.contact.phone_number = "+359896759292"
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.from_user.first_name = "Test"
    message.from_user.last_name = None
    message.from_user.username = "testuser"
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "test", "viewing_objects": []})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=True)

    with patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None):
        await on_phone_contact(message, state, lead_sink=sink)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "Заявка оформлена" in message.answer.call_args[0][0]
    sink.record_request.assert_awaited_once()
    kwargs = sink.record_request.call_args.kwargs
    assert kwargs["client_id"] == 123
    assert kwargs["service_key"] == "test"


async def test_on_phone_contact_without_sink_is_truthful():
    """Without a sink the bot must NOT claim the request was created (#3213)."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.contact = MagicMock()
    message.contact.phone_number = "+359896759292"
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "test", "viewing_objects": []})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    with patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None):
        await on_phone_contact(message, state, lead_sink=None)

    state.clear.assert_not_awaited()
    message.answer.assert_awaited_once()
    text = message.answer.call_args[0][0]
    assert "Заявка оформлена" not in text
    assert "не удалось сохранить" in text.lower()


async def test_on_phone_contact_sink_failure_is_truthful():
    """A sink that does not acknowledge must produce failure copy, not success."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.contact = MagicMock()
    message.contact.phone_number = "+359896759292"
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "test", "viewing_objects": []})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=False)

    with patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None):
        await on_phone_contact(message, state, lead_sink=sink)

    state.clear.assert_not_awaited()
    message.answer.assert_awaited_once()
    text = message.answer.call_args[0][0]
    assert "Заявка оформлена" not in text


async def test_on_phone_received_records_via_sink():
    """Text-input path forwards context (objects, date_range) to the sink."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "+380501234567"
    message.from_user = MagicMock()
    message.from_user.id = 77
    message.from_user.first_name = "Test"
    message.from_user.last_name = None
    message.from_user.username = None
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={
            "service_key": "viewing",
            "viewing_objects": [{"id": "obj-1"}],
            "date_range": "nearest",
        }
    )
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=True)

    await mod.on_phone_received(message, state, lead_sink=sink)

    state.clear.assert_awaited_once()
    assert "Заявка оформлена" in message.answer.call_args[0][0]
    kwargs = sink.record_request.call_args.kwargs
    assert kwargs["viewing_objects"] == [{"id": "obj-1"}]
    assert kwargs["date_range"] == "nearest"


async def test_process_valid_phone_never_logs_raw_phone(caplog):
    """Sink outcomes must be logged without raw phone values (#3213)."""
    import logging as logging_module
    from unittest.mock import MagicMock

    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 55
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "viewing"})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=True)

    with (
        patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None),
        caplog.at_level(logging_module.INFO, logger="telegram_bot.handlers.phone_collector"),
    ):
        await mod._process_valid_phone("+380501234567", message, state, lead_sink=sink)

    assert all("+380501234567" not in rec.getMessage() for rec in caplog.records)
    assert all("provided" in rec.getMessage() for rec in caplog.records)


async def test_on_phone_contact_no_contact_asks_manual_input():
    """on_phone_contact with no contact data should ask for manual input."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.contact = None
    message.answer = AsyncMock()
    state = MagicMock()

    await on_phone_contact(message, state)

    message.answer.assert_awaited_once()
    assert "вручную" in message.answer.call_args[0][0].lower()


# --- Phone cancel handling tests ---


async def test_on_phone_received_cancel_clears_state_and_sends_message():
    """Sending '❌ Отмена' in waiting_phone state clears FSM and sends cancel text."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "❌ Отмена"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    await mod.on_phone_received(message, state)

    state.clear.assert_awaited_once()
    answer_text = message.answer.call_args[0][0]
    assert answer_text == "Обращение отменено."


# ---------------------------------------------------------------------------
# Bookmarks capability gate on phone-collector keyboards (#3241 review fix)
# ---------------------------------------------------------------------------


class _BotWithoutFavorites:
    _favorites_service = None


class _BotWithFavorites:
    _favorites_service = object()


def _keyboard_texts(message_answer_mock) -> list[str]:
    kb = message_answer_mock.call_args.kwargs.get("reply_markup")
    assert kb is not None, "phone flow must restore the client reply keyboard"
    return [btn.text for row in kb.keyboard for btn in row]


async def test_phone_cancel_keyboard_omits_bookmarks_when_capability_off():
    """Cancelling the phone step must not re-advertise bookmarks without PostgreSQL."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "❌ Отмена"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    await mod.on_phone_received(message, state, property_bot=_BotWithoutFavorites())

    texts = _keyboard_texts(message.answer)
    assert not any("закладки" in t.lower() for t in texts)
    # Core menu actions stay reachable.
    assert any("Подобрать" in t for t in texts)


async def test_phone_cancel_keyboard_keeps_bookmarks_when_capability_on():
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "❌ Отмена"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    await mod.on_phone_received(message, state, property_bot=_BotWithFavorites())

    assert any("закладки" in t.lower() for t in _keyboard_texts(message.answer))


async def test_phone_success_keyboard_omits_bookmarks_when_capability_off():
    """After a sink-acknowledged submission the restored keyboard honours the gate."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "+380501234567"
    message.from_user = MagicMock()
    message.from_user.id = 91
    message.from_user.first_name = "Test"
    message.from_user.last_name = None
    message.from_user.username = None
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "viewing", "viewing_objects": []})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=True)

    with patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None):
        await mod.on_phone_received(
            message, state, lead_sink=sink, property_bot=_BotWithoutFavorites()
        )

    assert "Заявка оформлена" in message.answer.call_args[0][0]
    assert not any("закладки" in t.lower() for t in _keyboard_texts(message.answer))


async def test_phone_success_keyboard_keeps_bookmarks_when_capability_on():
    from unittest.mock import MagicMock

    message = MagicMock()
    message.text = "+380501234567"
    message.from_user = MagicMock()
    message.from_user.id = 92
    message.from_user.first_name = "Test"
    message.from_user.last_name = None
    message.from_user.username = None
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "viewing", "viewing_objects": []})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=True)

    with patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None):
        await mod.on_phone_received(
            message, state, lead_sink=sink, property_bot=_BotWithFavorites()
        )

    assert any("закладки" in t.lower() for t in _keyboard_texts(message.answer))


async def test_phone_contact_success_keyboard_omits_bookmarks_when_capability_off():
    """Contact-share path forwards property_bot so the gate applies there too."""
    from unittest.mock import MagicMock

    message = MagicMock()
    message.contact = MagicMock()
    message.contact.phone_number = "+359896759292"
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.from_user.first_name = "Test"
    message.from_user.last_name = None
    message.from_user.username = "testuser"
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"service_key": "test", "viewing_objects": []})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()

    sink = MagicMock()
    sink.record_request = AsyncMock(return_value=True)

    with patch("telegram_bot.handlers.phone_collector.get_phone_config", return_value=None):
        await on_phone_contact(message, state, lead_sink=sink, property_bot=_BotWithoutFavorites())

    assert not any("закладки" in t.lower() for t in _keyboard_texts(message.answer))


# Regression #3322: the lead request id is generated once per logical request
# and kept in FSM data — a failed-persistence retry reuses it (idempotent at
# the sink), while a post-success new submission starts a fresh id.
async def test_lead_request_id_is_stable_across_failed_retries():
    from types import SimpleNamespace

    from telegram_bot.handlers.phone_collector import _process_valid_phone

    class _FakeState:
        def __init__(self, data):
            self._data = dict(data)

        async def get_data(self):
            return dict(self._data)

        async def update_data(self, **kwargs):
            self._data.update(kwargs)

        async def clear(self):
            self._data.clear()

    class _FailingSink:
        def __init__(self):
            self.seen_ids = []

        async def record_request(self, **kwargs):
            self.seen_ids.append(kwargs["request_id"])
            return False  # persistence fails — user stays in FSM and retries

    sink = _FailingSink()
    state = _FakeState({"service_key": "viewing"})
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username=None, first_name="Ivan"),
        answer=AsyncMock(),
    )

    await _process_valid_phone("+380501234567", message, state, lead_sink=sink)
    await _process_valid_phone("+380501234567", message, state, lead_sink=sink)

    assert sink.seen_ids, "sink must have been attempted"
    assert len(sink.seen_ids) == 2
    assert sink.seen_ids[0] == sink.seen_ids[1]
    assert state._data["lead_request_id"] == sink.seen_ids[0]
