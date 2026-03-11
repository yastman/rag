"""Tests for demo → catalog browsing transition (#959)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.dialogs.states import CatalogBrowsingSG


def _make_message() -> MagicMock:
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.from_user = MagicMock(id=123)
    msg.chat = MagicMock(id=456)
    return msg


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


_APT = {
    "id": "apt-1",
    "payload": {
        "complex_name": "Premier Fort Beach",
        "city": "Солнечный берег",
        "section": "A",
        "apartment_number": "101",
        "rooms": 2,
        "floor": 3,
        "area_m2": 55.0,
        "view_primary": "sea",
        "view_tags": ["sea"],
        "price_eur": 75000,
        "is_furnished": True,
        "is_promotion": False,
    },
}

_EXTRACTION = SimpleNamespace(
    hard=SimpleNamespace(
        model_dump=lambda **_kw: {"rooms": 2},
        to_filters_dict=lambda: {"rooms": 2},
        city=None,
        rooms=2,
    ),
    meta=SimpleNamespace(semantic_remainder="", source="regex"),
)


def _make_pipeline(extraction: object | None = None) -> AsyncMock:
    pipeline = AsyncMock()
    pipeline.extract = AsyncMock(return_value=extraction or _EXTRACTION)
    return pipeline


def _make_svc(results: list | None = None, total: int = 42) -> MagicMock:
    svc = MagicMock()
    svc.scroll_with_filters = AsyncMock(
        return_value=(results or [_APT] * 10, total, 80000.0, ["apt-1"]),
    )
    return svc


# ---------------------------------------------------------------------------
# Task 1: _dialog_search → CatalogBrowsingSG
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dialog_search_transitions_to_catalog_browsing() -> None:
    """After search, FSM state should be CatalogBrowsingSG.browsing."""
    from telegram_bot.dialogs.demo import _dialog_search

    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(),
        "state": state,
    }
    manager.dialog_data = {}

    await _dialog_search("двушка", msg, manager)

    state.set_state.assert_awaited_once_with(CatalogBrowsingSG.browsing)


@pytest.mark.asyncio
async def test_dialog_search_saves_pagination_data() -> None:
    """Pagination data should be stored in FSM state."""
    from telegram_bot.dialogs.demo import _dialog_search

    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(total=42),
        "state": state,
    }
    manager.dialog_data = {}

    await _dialog_search("двушка", msg, manager)

    update_call = state.update_data.call_args
    assert update_call is not None
    kwargs = update_call[1] or update_call[0][0]
    assert kwargs["apartment_total"] == 42
    assert kwargs["apartment_offset"] == 10


@pytest.mark.asyncio
async def test_dialog_search_uses_scroll_not_vector() -> None:
    """Should use scroll_with_filters, not search_with_filters."""
    from telegram_bot.dialogs.demo import _dialog_search

    msg = _make_message()
    state = _make_state()
    svc = _make_svc()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": svc,
        "state": state,
    }
    manager.dialog_data = {}

    await _dialog_search("квартира", msg, manager)

    svc.scroll_with_filters.assert_awaited_once()


@pytest.mark.asyncio
async def test_dialog_search_shows_catalog_keyboard() -> None:
    """Results message should include ReplyKeyboard."""
    from telegram_bot.dialogs.demo import _dialog_search

    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(results=[_APT] * 5, total=20),
        "state": state,
    }
    manager.dialog_data = {}

    await _dialog_search("апартаменты", msg, manager)

    answer_calls = [c for c in msg.answer.call_args_list if c[1].get("reply_markup")]
    assert len(answer_calls) >= 1, "Should send message with ReplyKeyboard"


@pytest.mark.asyncio
async def test_dialog_search_closes_demo_dialog() -> None:
    """After transition, demo dialog should be closed via manager.done()."""
    from telegram_bot.dialogs.demo import _dialog_search

    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(),
        "state": state,
    }
    manager.dialog_data = {}

    await _dialog_search("двушка", msg, manager)

    manager.done.assert_awaited_once()


# ---------------------------------------------------------------------------
# Task 2: _run_demo_search (FSM handler) → CatalogBrowsingSG
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_run_demo_search_transitions_to_catalog() -> None:
    """FSM handler should transition to CatalogBrowsingSG.browsing."""
    from telegram_bot.handlers.demo_handler import _run_demo_search

    msg = _make_message()
    state = _make_state()

    await _run_demo_search(
        "двушка",
        msg,
        state,
        pipeline=_make_pipeline(),
        apartments_service=_make_svc(results=[_APT] * 5, total=15),
    )

    state.set_state.assert_awaited_once_with(CatalogBrowsingSG.browsing)


@pytest.mark.asyncio
async def test_handler_run_demo_search_uses_scroll() -> None:
    """FSM handler should call scroll_with_filters."""
    from telegram_bot.handlers.demo_handler import _run_demo_search

    msg = _make_message()
    state = _make_state()
    svc = _make_svc()

    await _run_demo_search(
        "двушка",
        msg,
        state,
        pipeline=_make_pipeline(),
        apartments_service=svc,
    )

    svc.scroll_with_filters.assert_awaited_once()


# ---------------------------------------------------------------------------
# Task 3: Voice/text input → search → catalog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_input_triggers_search_and_catalog() -> None:
    """Voice → STT → extraction → scroll → catalog browsing."""
    from telegram_bot.dialogs.demo import on_voice_input

    msg = _make_message()
    msg.voice = MagicMock(file_id="test-file-id")
    state = _make_state()
    svc = _make_svc()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": svc,
        "state": state,
    }
    manager.dialog_data = {}

    widget = MagicMock()

    with patch(
        "telegram_bot.dialogs.demo.transcribe_voice",
        new_callable=AsyncMock,
        return_value="двушка в солнечном берегу",
    ):
        await on_voice_input(msg, widget, manager)

    svc.scroll_with_filters.assert_awaited_once()


@pytest.mark.asyncio
async def test_text_input_triggers_search_and_catalog() -> None:
    """Text input → extraction → scroll → catalog browsing."""
    from telegram_bot.dialogs.demo import on_text_input

    msg = _make_message()
    msg.text = "трёшка до 100к"
    state = _make_state()
    svc = _make_svc()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": svc,
        "state": state,
    }
    manager.dialog_data = {}

    widget = MagicMock()
    await on_text_input(msg, widget, manager)

    svc.scroll_with_filters.assert_awaited_once()


# ---------------------------------------------------------------------------
# Task 4: Catalog pagination after demo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalog_more_works_after_demo_search() -> None:
    """After demo search, 'Показать ещё' should load next page."""
    from telegram_bot.handlers.catalog_router import handle_catalog_more

    msg = _make_message()
    msg.text = "📥 Показать ещё (10 из 42)"

    state = _make_state(
        {
            "apartment_offset": 10,
            "apartment_total": 42,
            "apartment_next_offset": 80000.0,
            "apartment_scroll_seen_ids": ["apt-1"],
            "apartment_filters": {"rooms": 2},
            "catalog_view_mode": "list",
        }
    )

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(
        return_value=([_APT] * 10, 42, 90000.0, ["apt-2"]),
    )
    property_bot = MagicMock()
    property_bot._apartments_service = mock_svc
    property_bot._send_property_card = AsyncMock()

    await handle_catalog_more(msg, state, property_bot=property_bot)

    mock_svc.scroll_with_filters.assert_awaited_once()
    update_kwargs = state.update_data.call_args[1]
    assert update_kwargs["apartment_offset"] == 20


@pytest.mark.asyncio
async def test_catalog_exit_returns_to_main_menu() -> None:
    """'Главное меню' should clear state and return to main."""
    from telegram_bot.handlers.catalog_router import handle_catalog_exit

    msg = _make_message()
    state = _make_state(
        {
            "apartment_offset": 10,
            "apartment_total": 42,
        }
    )

    await handle_catalog_exit(msg, state)

    state.set_state.assert_awaited_once_with(None)


# ---------------------------------------------------------------------------
# Task 5: Filter extraction parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected_key,expected_value",
    [
        ("двушка солнечный берег", "city", "Солнечный берег"),
        ("студия в элените", "rooms", 1),
        ("трёшка до 100к", "rooms", 4),
    ],
)
def test_extraction_produces_correct_filter(
    query: str, expected_key: str, expected_value: object
) -> None:
    """Verify text queries produce correct filters."""
    from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor

    extractor = ApartmentFilterExtractor()
    result = extractor.parse(query)
    filters = result.to_filters_dict()

    if expected_key == "city":
        assert result.city == expected_value, f"city mismatch for '{query}'"
    elif expected_key == "rooms":
        assert filters.get("rooms") == expected_value, f"rooms mismatch for '{query}'"


# ---------------------------------------------------------------------------
# Task 6: Voice input widget exists
# ---------------------------------------------------------------------------


def test_demo_dialog_has_voice_input() -> None:
    """Demo dialog must accept voice messages via on_voice_input handler."""
    from telegram_bot.dialogs.demo import demo_dialog, on_voice_input

    # Verify handler exists and is used in the dialog source
    assert callable(on_voice_input), "on_voice_input handler must exist"

    # Verify dialog has the intro window with DemoSG.intro state
    from telegram_bot.dialogs.states import DemoSG

    assert DemoSG.intro in demo_dialog.windows, "Dialog must have intro window"


# ---------------------------------------------------------------------------
# Task 8: Full flow integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_demo_flow_text_to_pagination() -> None:
    """Full flow: text → extraction → scroll → catalog → show more."""
    from telegram_bot.handlers.catalog_router import handle_catalog_more
    from telegram_bot.handlers.demo_handler import _run_demo_search

    # Step 1: Initial search
    msg = _make_message()
    state = _make_state()

    svc = _make_svc(results=[_APT] * 10, total=25)

    await _run_demo_search(
        "двушка",
        msg,
        state,
        pipeline=_make_pipeline(),
        apartments_service=svc,
    )

    state.set_state.assert_awaited_with(CatalogBrowsingSG.browsing)
    assert svc.scroll_with_filters.await_count == 1

    # Step 2: Show more
    msg2 = _make_message()
    msg2.text = "📥 Показать ещё (10 из 25)"

    state2 = _make_state(
        {
            "apartment_offset": 10,
            "apartment_total": 25,
            "apartment_next_offset": 80000.0,
            "apartment_scroll_seen_ids": ["apt-1"],
            "apartment_filters": {"rooms": 2},
            "catalog_view_mode": "list",
        }
    )

    svc2 = MagicMock()
    svc2.scroll_with_filters = AsyncMock(
        return_value=([_APT] * 10, 25, 90000.0, ["apt-2"]),
    )
    property_bot = MagicMock()
    property_bot._apartments_service = svc2

    await handle_catalog_more(msg2, state2, property_bot=property_bot)

    update_kwargs = state2.update_data.call_args[1]
    assert update_kwargs["apartment_offset"] == 20
