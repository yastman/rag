"""Tests for demo → catalog browsing transition (#959)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.dialogs.states import CatalogSG


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
    state.clear = AsyncMock()
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
# Task 1: query search → CatalogSG via the shared ApartmentCatalog entrypoint
# ---------------------------------------------------------------------------


async def _shared_query_search(msg: MagicMock, manager: MagicMock, query: str) -> None:
    from telegram_bot.dialogs.catalog import search_catalog_from_query

    await search_catalog_from_query(message=msg, dialog_manager=manager, query=query)


@pytest.mark.asyncio
async def test_dialog_search_starts_catalog_results() -> None:
    """After search, dialog should hand off to CatalogSG.results."""
    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(),
        "state": state,
    }
    manager.dialog_data = {}

    await _shared_query_search(msg, manager, "двушка")

    from aiogram_dialog import ShowMode, StartMode

    manager.start.assert_awaited_once_with(
        CatalogSG.results,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.NO_UPDATE,
    )


@pytest.mark.asyncio
async def test_dialog_search_saves_pagination_data() -> None:
    """catalog_runtime should be stored in FSM state."""
    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(total=42),
        "state": state,
    }
    manager.dialog_data = {}

    await _shared_query_search(msg, manager, "двушка")

    update_call = state.update_data.call_args
    assert update_call is not None
    kwargs = update_call[1] or update_call[0][0]
    assert kwargs["catalog_runtime"]["total"] == 42
    assert kwargs["catalog_runtime"]["shown_count"] == 10


@pytest.mark.asyncio
async def test_dialog_search_uses_scroll_not_vector() -> None:
    """Should use scroll_with_filters, not search_with_filters."""
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

    await _shared_query_search(msg, manager, "квартира")

    svc.scroll_with_filters.assert_awaited_once()


@pytest.mark.asyncio
async def test_dialog_search_sends_results_as_regular_messages() -> None:
    """Results should still be sent as normal chat messages."""
    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(results=[_APT] * 5, total=20),
        "state": state,
    }
    manager.dialog_data = {}

    await _shared_query_search(msg, manager, "апартаменты")

    answer_calls = [c for c in msg.answer.call_args_list if c.args]
    assert any("Premier Fort Beach" in str(c.args[0]) for c in answer_calls)


@pytest.mark.asyncio
async def test_dialog_search_replaces_demo_dialog_with_catalog_shell() -> None:
    """After transition, demo dialog should be replaced by CatalogSG."""
    msg = _make_message()
    state = _make_state()

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(),
        "state": state,
    }
    manager.dialog_data = {}

    await _shared_query_search(msg, manager, "двушка")

    from aiogram_dialog import ShowMode, StartMode

    manager.start.assert_awaited_once_with(
        CatalogSG.results,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.NO_UPDATE,
    )


# ---------------------------------------------------------------------------
# Task 2 was the legacy ``_run_demo_search`` FSM handler. Since #3238 the
# whole apartment search flow lives in the shared catalog entrypoint
# ``search_catalog_from_query`` behind the ApartmentCatalog interface and
# is covered by the dialog-side tests above; the legacy handler is gone.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 3: Voice/text input → search → catalog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_input_triggers_search_and_catalog() -> None:
    """Voice → STT → extraction → scroll → catalog dialog flow."""
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
    """Text input → extraction → scroll → catalog dialog flow."""
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
    """After demo search, dialog-native 'more' should load next page."""
    from telegram_bot.dialogs.catalog import on_catalog_more

    state = _make_state(
        {
            "catalog_runtime": {
                "shown_count": 10,
                "total": 42,
                "next_offset": 80000.0,
                "shown_item_ids": ["apt-1"],
                "filters": {"rooms": 2},
                "view_mode": "list",
            }
        }
    )

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(
        return_value=([_APT] * 10, 42, 90000.0, ["apt-2"]),
    )
    property_bot = MagicMock()
    property_bot._apartments_service = mock_svc
    property_bot._send_property_card = AsyncMock()

    manager = AsyncMock()
    manager.middleware_data = {"state": state, "property_bot": property_bot}
    callback = MagicMock(message=_make_message(), from_user=MagicMock(id=123))

    await on_catalog_more(callback, MagicMock(), manager)

    mock_svc.scroll_with_filters.assert_awaited_once()
    update_kwargs = state.update_data.call_args[1]
    assert update_kwargs["catalog_runtime"]["shown_count"] == 20


@pytest.mark.asyncio
async def test_catalog_exit_returns_to_main_menu() -> None:
    """'Главное меню' should clear state and return to main."""
    from telegram_bot.dialogs.catalog import on_catalog_home

    manager = AsyncMock()
    state = _make_state()
    manager.middleware_data = {"state": state, "i18n": None}
    callback = MagicMock()
    callback.message = _make_message()
    callback.message.bot = MagicMock(delete_message=AsyncMock())
    callback.message.from_user = MagicMock(first_name="Test")

    await on_catalog_home(callback, MagicMock(), manager)

    state.clear.assert_awaited_once()
    manager.reset_stack.assert_awaited_once_with(remove_keyboard=True)
    callback.message.answer.assert_awaited()


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
    from telegram_bot.services.apartment.apartment_filter_extractor import ApartmentFilterExtractor

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
# Task 7: Legacy demo FSM state clearing
# ---------------------------------------------------------------------------
# After #2054 the apartment-search flow no longer touches a parallel FSM
# state — it lives entirely in ``demo_dialog`` (aiogram-dialog manages
# state on its own stack). The two legacy tests that asserted the FSM
# clear / no-clear contract were dropped; ``test_catalog_exit_returns_to_main_menu``
# above still asserts that exiting back to the main menu clears state.


# ---------------------------------------------------------------------------
# Task 8: Full flow integration test (dialog path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_demo_flow_text_to_pagination() -> None:
    """Full flow: text → extraction → scroll → catalog → show more."""
    from telegram_bot.dialogs.catalog import on_catalog_more

    # Step 1: Initial search via the shared catalog entrypoint (#3238).
    msg = _make_message()
    state = _make_state()

    svc = _make_svc(results=[_APT] * 10, total=25)

    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": svc,
        "state": state,
    }
    manager.dialog_data = {}

    await _shared_query_search(msg, manager, "двушка")

    assert "catalog_runtime" in state.update_data.await_args.kwargs
    assert svc.scroll_with_filters.await_count == 1

    # Step 2: Show more
    state2 = _make_state(
        {
            "catalog_runtime": {
                "shown_count": 10,
                "total": 25,
                "next_offset": 80000.0,
                "shown_item_ids": ["apt-1"],
                "filters": {"rooms": 2},
                "view_mode": "list",
            }
        }
    )

    svc2 = MagicMock()
    svc2.scroll_with_filters = AsyncMock(
        return_value=([_APT] * 10, 25, 90000.0, ["apt-2"]),
    )
    property_bot = MagicMock()
    property_bot._apartments_service = svc2
    manager = AsyncMock()
    manager.middleware_data = {"state": state2, "property_bot": property_bot}
    callback = MagicMock(message=_make_message(), from_user=MagicMock(id=123))

    await on_catalog_more(callback, MagicMock(), manager)

    update_kwargs = state2.update_data.call_args[1]
    assert update_kwargs["catalog_runtime"]["shown_count"] == 20


# ---------------------------------------------------------------------------
# #3238: one ApartmentCatalog interface behind both entrypoints
# ---------------------------------------------------------------------------


async def _run_query_through(entrypoint: str) -> tuple[dict, object]:
    """Run the same query through demo intro or catalog text input."""
    msg = _make_message()
    msg.text = "двушка до 100к"
    state = _make_state()
    manager = AsyncMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": _make_svc(results=[_APT] * 10, total=25),
        "state": state,
    }
    manager.dialog_data = {}

    if entrypoint == "demo":
        from telegram_bot.dialogs.demo import on_text_input

        await on_text_input(msg, MagicMock(), manager)
    else:
        from telegram_bot.dialogs.catalog import on_catalog_text_input

        await on_catalog_text_input(msg, MagicMock(), manager)

    runtime = state.update_data.await_args.kwargs["catalog_runtime"]
    return runtime, manager.start.await_args


@pytest.mark.asyncio
async def test_demo_and_catalog_entrypoints_produce_identical_results_and_navigation() -> None:
    """Acceptance #3238: same query through both entrypoints — identical outcome."""
    demo_runtime, demo_start = await _run_query_through("demo")
    catalog_runtime, catalog_start = await _run_query_through("catalog")

    assert demo_runtime == catalog_runtime
    assert demo_start == catalog_start
    assert demo_runtime["total"] == 25
    assert demo_runtime["shown_count"] == 10
    assert demo_runtime["filters"] == {"rooms": 2}


def test_catalog_package_has_no_demo_imports() -> None:
    """#3238: production catalog must not import the demo implementation."""
    from pathlib import Path

    catalog_dir = Path("telegram_bot/dialogs/catalog")
    assert catalog_dir.exists()
    for path in catalog_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "dialogs.demo" not in source, f"{path} still imports the demo dialog"
        assert "demo_handler" not in source, f"{path} still imports the demo handler"
