"""Tests for dynamic funnel options from Qdrant."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


async def test_get_city_options_from_service() -> None:
    """get_city_options loads cities from ApartmentsService when available."""
    from telegram_bot.dialogs.funnel import get_city_options

    mock_svc = MagicMock()
    mock_svc.get_distinct_values = AsyncMock(
        return_value=["Свети Влас", "Солнечный берег", "Элените"]
    )
    manager = SimpleNamespace(
        middleware_data={"apartments_service": mock_svc},
        dialog_data={},
    )

    result = await get_city_options(dialog_manager=manager)
    items = result["items"]

    # Should contain service cities + "Любой город"
    city_names = [item[0] for item in items]
    assert "Свети Влас" in city_names
    assert "Солнечный берег" in city_names
    assert items[-1] == ("Любой город", "any")
    mock_svc.get_distinct_values.assert_awaited_once_with("city")


async def test_get_city_options_fallback_on_no_service() -> None:
    """get_city_options falls back to hardcoded list when service unavailable."""
    from telegram_bot.dialogs.funnel import get_city_options

    manager = SimpleNamespace(
        middleware_data={},
        dialog_data={},
    )

    result = await get_city_options(dialog_manager=manager)
    items = result["items"]
    assert len(items) >= 2  # at least 1 city + "Любой город"
    assert items[-1][1] == "any"


async def test_get_city_options_fallback_on_error() -> None:
    """get_city_options falls back to hardcoded on service error."""
    from telegram_bot.dialogs.funnel import get_city_options

    mock_svc = MagicMock()
    mock_svc.get_distinct_values = AsyncMock(side_effect=Exception("Qdrant down"))
    manager = SimpleNamespace(
        middleware_data={"apartments_service": mock_svc},
        dialog_data={},
    )

    result = await get_city_options(dialog_manager=manager)
    items = result["items"]
    assert len(items) >= 2
    assert items[-1][1] == "any"


async def test_get_pref_complex_options_from_service() -> None:
    """get_pref_complex_options loads complexes dynamically."""
    from telegram_bot.dialogs.funnel import get_pref_complex_options

    mock_svc = MagicMock()
    mock_svc.get_distinct_values = AsyncMock(return_value=["Crown Fort Club", "Premier Fort Beach"])
    manager = SimpleNamespace(
        middleware_data={"apartments_service": mock_svc},
        dialog_data={},
    )

    result = await get_pref_complex_options(dialog_manager=manager)
    items = result["items"]
    assert ("Crown Fort Club", "Crown Fort Club") in items
    assert items[-1] == ("Любой комплекс", "any")


async def test_get_pref_section_options_from_service() -> None:
    """get_pref_section_options loads sections dynamically."""
    from telegram_bot.dialogs.funnel import get_pref_section_options

    mock_svc = MagicMock()
    mock_svc.get_distinct_values = AsyncMock(return_value=["A", "B-1", "C-2"])
    manager = SimpleNamespace(
        middleware_data={"apartments_service": mock_svc},
        dialog_data={},
    )

    result = await get_pref_section_options(dialog_manager=manager)
    items = result["items"]
    assert ("A", "A") in items
    assert ("B-1", "B-1") in items
    assert items[-1] == ("Любая секция", "any")
