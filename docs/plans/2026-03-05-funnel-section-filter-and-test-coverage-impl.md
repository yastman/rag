# Funnel Section Filter + Test Coverage — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add section filter to apartment funnel, replace custom buttons with SDK SwitchTo, cover all test gaps (~52 tests).

**Architecture:** Extend existing aiogram-dialog funnel with new `pref_section` state/window. Replace 8 `Button+on_click(switch_to)` with SDK `SwitchTo`. TDD: write failing tests first, then implement.

**Tech Stack:** Python 3.12, aiogram-dialog (Select, SwitchTo, Multiselect), Qdrant (keyword MatchValue), pytest + pytest-asyncio

**Design doc:** `docs/plans/2026-03-05-funnel-section-filter-and-test-coverage-design.md`

> **Review note (2026-03-05):** plan point-fixed after repo + SDK verification:
> - `on_pref_view_selected("any")` currently stores `"any"` (does not clear to `None`) in existing code.
> - aiogram-dialog `SwitchTo` target is checked via public `widget.state` (not private `_state`).
> - after removing `on_pref_back_to_menu`, related test must be migrated to `SwitchTo` structure checks.
> - section options aligned to dataset values from `data/apartments.csv` as-of 2026-03-05.
> - final validation gate aligned to AGENTS requirements (`make check` + `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`).

---

## Task 1: Tests for existing gaps — handlers & navigation

**Files:**
- Modify: `tests/unit/dialogs/test_funnel.py` (append)

**Step 1: Write failing tests for pref_view, pref_category routing, back, pagination**

```python
# --- pref_view handler ---


async def test_pref_view_selected_saves_and_returns():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_view_selected(MagicMock(), SimpleNamespace(), manager, "sea")
    assert manager.dialog_data["view"] == "sea"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


async def test_pref_view_any_keeps_any_marker():
    manager = SimpleNamespace(dialog_data={"view": "sea"}, switch_to=AsyncMock())
    await funnel_module.on_pref_view_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["view"] == "any"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


# --- pref_category routing (missing) ---


async def test_pref_category_view_switches_to_pref_view():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(MagicMock(), SimpleNamespace(), manager, "view")
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_view)


async def test_pref_category_furnished_switches_to_pref_furnished():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "furnished"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_furnished)


async def test_pref_category_promotion_switches_to_pref_promotion():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "promotion"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_promotion)


# --- Back navigation ---


async def test_pref_back_to_menu_switches_to_preferences():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_back_to_menu(MagicMock(), SimpleNamespace(), manager)
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


# --- Pagination ---


async def test_results_more_increments_page_and_offset():
    manager = SimpleNamespace(
        dialog_data={"scroll_next_offset": "uuid-next", "scroll_page": 1},
    )
    callback = MagicMock()
    callback.answer = AsyncMock()
    await funnel_module.on_results_more(callback, SimpleNamespace(), manager)
    assert manager.dialog_data["scroll_offset"] == "uuid-next"
    assert manager.dialog_data["scroll_page"] == 2


async def test_results_more_no_next_offset_answers_all_shown():
    manager = SimpleNamespace(dialog_data={})
    callback = MagicMock()
    callback.answer = AsyncMock()
    await funnel_module.on_results_more(callback, SimpleNamespace(), manager)
    callback.answer.assert_awaited_once_with("Все результаты показаны")


# --- property_type return_to_summary ---


async def test_property_type_return_to_summary():
    manager = SimpleNamespace(dialog_data={"_return_to_summary": True}, switch_to=AsyncMock())
    await funnel_module.on_property_type_selected(
        MagicMock(), SimpleNamespace(), manager, "2bed"
    )
    assert manager.dialog_data["property_type"] == "2bed"
    assert "_return_to_summary" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.summary)
```

**Step 2: Run tests to verify they pass (these test existing code)**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py -v -k "pref_view or pref_category_view or pref_category_furnished or pref_category_promotion or pref_back_to_menu_switches or results_more or property_type_return" --timeout=10`
Expected: ALL PASS (testing existing handlers)

**Step 3: Commit**

```bash
git add tests/unit/dialogs/test_funnel.py
git commit -m "test(funnel): cover pref_view, category routing, back, pagination handlers"
```

---

## Task 2: Tests for existing gaps — getters & zero suggestions & summary

**Files:**
- Modify: `tests/unit/dialogs/test_funnel.py` (append)

**Step 1: Write tests for getter content, zero suggestions, summary display**

```python
# --- Getter content validation ---


async def test_pref_floor_options_has_4_plus_any():
    result = await funnel_module.get_pref_floor_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 5
    assert set(keys) == {"low", "mid", "high", "top", "any"}


async def test_pref_view_options_has_4_plus_any():
    result = await funnel_module.get_pref_view_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 5
    assert set(keys) == {"sea", "pool", "garden", "forest", "any"}


async def test_pref_furnished_options_has_3():
    result = await funnel_module.get_pref_furnished_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 3
    assert set(keys) == {"yes", "no", "any"}


async def test_pref_promotion_options_has_2():
    result = await funnel_module.get_pref_promotion_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 2
    assert set(keys) == {"yes", "any"}


# --- Zero suggestions (missing cases) ---


async def test_zero_suggestion_rm_view():
    manager = SimpleNamespace(
        dialog_data={"view": "sea", "scroll_offset": "x", "scroll_next_offset": "y"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_view"
    )
    assert "view" not in manager.dialog_data
    assert manager.dialog_data.get("scroll_offset") is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


async def test_zero_suggestion_rm_furnished():
    manager = SimpleNamespace(
        dialog_data={"is_furnished": "yes", "scroll_offset": "x"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_furnished"
    )
    assert "is_furnished" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


async def test_zero_suggestion_rm_promotion():
    manager = SimpleNamespace(
        dialog_data={"is_promotion": "yes", "scroll_offset": "x"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_promotion"
    )
    assert "is_promotion" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


async def test_zero_suggestion_rm_budget():
    manager = SimpleNamespace(
        dialog_data={"budget": "high", "scroll_offset": "x"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_budget"
    )
    assert manager.dialog_data["budget"] == "any"
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


# --- Summary display (missing) ---


async def test_summary_shows_furnished_yes():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "any", "property_type": "any", "budget": "any",
                         "is_furnished": "yes"},
            middleware_data={},
        ),
    )
    assert "С мебелью" in result["summary_text"]


async def test_summary_shows_furnished_no():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "any", "property_type": "any", "budget": "any",
                         "is_furnished": "no"},
            middleware_data={},
        ),
    )
    assert "Без мебели" in result["summary_text"]


async def test_summary_shows_promotion():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "any", "property_type": "any", "budget": "any",
                         "is_promotion": "yes"},
            middleware_data={},
        ),
    )
    assert "Акции" in result["summary_text"]
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py -v -k "pref_floor_options_has_4 or pref_view_options_has_4 or pref_furnished_options_has_3 or pref_promotion_options_has_2 or zero_suggestion_rm_view or zero_suggestion_rm_furnished or zero_suggestion_rm_promotion or zero_suggestion_rm_budget or summary_shows_furnished or summary_shows_promotion" --timeout=10`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/unit/dialogs/test_funnel.py
git commit -m "test(funnel): cover getters, zero suggestions, summary furnished/promotion display"
```

---

## Task 3: Tests for _build_apartment_filter (Qdrant layer)

**Files:**
- Modify: `tests/unit/services/test_apartments_service.py` (append)

**Step 1: Read existing tests first**

Run: `uv run pytest tests/unit/services/test_apartments_service.py --collect-only -q` to see what's already covered.

**Step 2: Write tests for each Qdrant filter type**

```python
from qdrant_client import models

from telegram_bot.services.apartments_service import _build_apartment_filter


class TestBuildApartmentFilter:
    """Tests for _build_apartment_filter() — Qdrant filter construction."""

    def test_keyword_exact_match(self):
        result = _build_apartment_filter({"section": "D-1"})
        assert result is not None
        assert len(result.must) == 1
        cond = result.must[0]
        assert cond.key == "section"
        assert cond.match.value == "D-1"

    def test_list_match_any(self):
        result = _build_apartment_filter({"view_tags": ["sea", "pool"]})
        assert result is not None
        cond = result.must[0]
        assert cond.key == "view_tags"
        assert cond.match.any == ["sea", "pool"]

    def test_range_filter(self):
        result = _build_apartment_filter({"price_eur": {"gte": 100000, "lte": 200000}})
        assert result is not None
        cond = result.must[0]
        assert cond.key == "price_eur"
        assert cond.range.gte == 100000
        assert cond.range.lte == 200000

    def test_bool_before_int(self):
        """bool must be checked before int — isinstance(True, int) is True in Python."""
        result = _build_apartment_filter({"is_furnished": True})
        assert result is not None
        cond = result.must[0]
        assert cond.match.value is True
        assert not isinstance(cond.range, models.Range) if hasattr(cond, "range") else True

    def test_combined_must(self):
        result = _build_apartment_filter({
            "city": "Элените",
            "rooms": 3,
            "price_eur": {"gte": 100000},
        })
        assert result is not None
        assert len(result.must) == 3

    def test_empty_returns_none(self):
        assert _build_apartment_filter({}) is None

    def test_none_returns_none(self):
        assert _build_apartment_filter(None) is None
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/services/test_apartments_service.py -v -k "TestBuildApartmentFilter" --timeout=10`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/unit/services/test_apartments_service.py
git commit -m "test(apartments): cover _build_apartment_filter for all Qdrant condition types"
```

---

## Task 4: SwitchTo refactor — replace custom Button+handler with SDK

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py:13-21` (imports)
- Modify: `telegram_bot/dialogs/funnel.py:654-669` (delete on_pref_back_to_menu, on_summary_change, on_summary_refine)
- Modify: `telegram_bot/dialogs/funnel.py:1032-1150` (dialog windows)

**Step 1: Add SwitchTo import**

In `telegram_bot/dialogs/funnel.py:13-21`, add `SwitchTo` to imports:

```python
from aiogram_dialog.widgets.kbd import (
    Back,
    Button,
    Cancel,
    Column,
    ManagedMultiselect,
    Multiselect,
    Select,
    SwitchTo,
)
```

**Step 2: Replace 6 sub-option back buttons**

Replace `Button(Format("{btn_back}"), id="pref_floor_back", on_click=on_pref_back_to_menu)` with:
```python
SwitchTo(Format("{btn_back}"), id="pref_floor_back", state=FunnelSG.preferences)
```

Do the same for: `pref_view_back`, `pref_furn_back`, `pref_promo_back`, `pref_area_back`, `pref_cplx_back`.

**Step 3: Replace 2 summary buttons**

Replace lines 1137-1146:
```python
        SwitchTo(
            Format("✏️ Изменить параметры"),
            id="change",
            state=FunnelSG.change_filter,
        ),
        SwitchTo(
            Format("⚙️ Доп. пожелания"),
            id="refine",
            state=FunnelSG.preferences,
        ),
```

**Step 4: Delete 3 handlers**

Delete `on_pref_back_to_menu` (lines 654-660), `on_summary_change` (lines 869-875), `on_summary_refine` (lines 860-866).

**Step 5: Run all existing tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py tests/unit/dialogs/test_funnel_results.py -v --timeout=30`
Expected: Most PASS. Fix tests that reference deleted handlers (update `test_pref_back_to_menu_switches_to_preferences`, `test_on_summary_refine_goes_to_preferences`, `test_on_summary_change_goes_to_change_filter` — replace with `SwitchTo` structure tests).

**Step 6: Update tests for SwitchTo**

Replace handler tests with structural tests:

```python
def test_switchto_change_in_summary_targets_change_filter():
    """SwitchTo 'change' in summary window targets FunnelSG.change_filter."""
    from aiogram_dialog.widgets.kbd import SwitchTo as SwitchToWidget

    summary_window = funnel_dialog.windows[FunnelSG.summary]
    found = False
    for widget in summary_window.keyboard.buttons:
        if isinstance(widget, SwitchToWidget) and widget.widget_id == "change":
            assert widget.state == FunnelSG.change_filter
            found = True
            break
    assert found, "SwitchTo 'change' not found in summary window"


def test_switchto_refine_in_summary_targets_preferences():
    """SwitchTo 'refine' in summary window targets FunnelSG.preferences."""
    from aiogram_dialog.widgets.kbd import SwitchTo as SwitchToWidget

    summary_window = funnel_dialog.windows[FunnelSG.summary]
    found = False
    for widget in summary_window.keyboard.buttons:
        if isinstance(widget, SwitchToWidget) and widget.widget_id == "refine":
            assert widget.state == FunnelSG.preferences
            found = True
            break
    assert found, "SwitchTo 'refine' not found in summary window"


def test_switchto_back_in_pref_floor_targets_preferences():
    """SwitchTo back button in pref_floor targets FunnelSG.preferences."""
    from aiogram_dialog.widgets.kbd import SwitchTo as SwitchToWidget

    floor_window = funnel_dialog.windows[FunnelSG.pref_floor]
    found = False
    for widget in floor_window.keyboard.buttons:
        if isinstance(widget, SwitchToWidget) and widget.widget_id == "pref_floor_back":
            assert widget.state == FunnelSG.preferences
            found = True
            break
    assert found, "SwitchTo 'pref_floor_back' not found in pref_floor window"
```

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/dialogs/ -n auto --dist=worksteal -v --timeout=30`
Expected: ALL PASS

**Step 8: Lint check**

Run: `make check`
Expected: PASS

**Step 9: Commit**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel.py
git commit -m "refactor(funnel): replace 8 Button+handler with SDK SwitchTo widgets"
```

---

## Task 5: Add section filter — state + constants + getter + handler

**Files:**
- Modify: `telegram_bot/dialogs/states.py:38` (add pref_section State)
- Modify: `telegram_bot/dialogs/funnel.py` (constants, getter, handler, routing, filters, summary, zero suggestions)

**Step 1: Write failing tests**

Append to `tests/unit/dialogs/test_funnel.py`:

```python
# --- Section filter ---


async def test_pref_section_options_has_sections_plus_any():
    result = await funnel_module.get_pref_section_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert "D-1" in keys
    assert "any" in keys
    assert len(items) == 27  # 26 unique sections from CSV + "any" (as-of 2026-03-05)


async def test_pref_section_selected_saves_and_returns():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_section_selected(MagicMock(), SimpleNamespace(), manager, "D-1")
    assert manager.dialog_data["section"] == "D-1"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


async def test_pref_section_any_clears_value():
    manager = SimpleNamespace(dialog_data={"section": "D-1"}, switch_to=AsyncMock())
    await funnel_module.on_pref_section_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["section"] is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


async def test_pref_category_section_switches_to_pref_section():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "section"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_section)


async def test_preferences_options_has_7_categories():
    result = await funnel_module.get_preferences_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    items = result["items"]
    ids = [item_id for _, item_id in items]
    assert "section" in ids
    assert len(items) == 7


async def test_preferences_section_syncs_widget_state():
    widget_data: dict[str, Any] = {}
    ctx = SimpleNamespace(widget_data=widget_data)
    manager = SimpleNamespace(
        dialog_data={"section": "D-1"},
        current_context=lambda: ctx,
    )
    await funnel_module.get_preferences_options(middleware_data={}, dialog_manager=manager)
    checked = widget_data.get(funnel_module._PREF_MS_ID, [])
    assert "section" in checked


def test_funnel_has_pref_section_window():
    windows = funnel_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FunnelSG.pref_section in states
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py -v -k "section" --timeout=10`
Expected: FAIL — `pref_section` not in FunnelSG, functions don't exist

**Step 3: Add state**

In `telegram_bot/dialogs/states.py`, after line 38 (`pref_complex`), add:
```python
    pref_section = State()  # Step 4g: секция sub-options
```

**Step 4: Add constants, getter, handler, routing to funnel.py**

Add `_SECTION_OPTIONS` after `_COMPLEX_OPTIONS` (line 48).
Source-of-truth: unique values from `data/apartments.csv` (as-of 2026-03-05), plus `"any"`:
```python
_SECTION_OPTIONS: list[tuple[str, str]] = [
    ("A", "A"),
    ("A-2", "A-2"),
    ("A-A", "A-A"),
    ("A-B", "A-B"),
    ("B", "B"),
    ("B-1", "B-1"),
    ("B-2", "B-2"),
    ("B-3", "B-3"),
    ("B-5", "B-5"),
    ("B-6", "B-6"),
    ("B-V", "B-V"),
    ("C-2", "C-2"),
    ("C-5", "C-5"),
    ("D-1", "D-1"),
    ("D-2", "D-2"),
    ("D-3", "D-3"),
    ("E-1", "E-1"),
    ("E-2", "E-2"),
    ("E-3", "E-3"),
    ("E-4", "E-4"),
    ("F-1", "F-1"),
    ("F-2", "F-2"),
    ("F-3", "F-3"),
    ("F-4", "F-4"),
    ("V-D", "V-D"),
    ("V-G", "V- G"),  # label normalized; payload value keeps dataset spelling
    ("Любая секция", "any"),
]
```

Add `("📍 Секция", "section")` to `_PREF_ITEMS` (line 141):
```python
_PREF_ITEMS: list[tuple[str, str]] = [
    ("🏢 Этаж", "floor"),
    ("🌅 Вид", "view"),
    ("📐 Площадь", "area"),
    ("🛋 Мебель", "furnished"),
    ("🏷 Акции", "promotion"),
    ("🏘 Комплекс", "complex"),
    ("📍 Секция", "section"),
]
```

Add section to `_compute_active_pref_categories` (after line 277):
```python
    if data.get("section") and data["section"] != "any":
        checked.append("section")
```

Add getter (after `get_pref_complex_options`):
```python
async def get_pref_section_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for section sub-options in preferences."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {"title": "Выберите секцию:", "items": _SECTION_OPTIONS, "btn_back": btn_back}
```

Add handler (after `on_pref_complex_selected`):
```python
async def on_pref_section_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save section preference and return to preferences menu."""
    manager.dialog_data["section"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)
```

Add routing in `on_pref_category_selected` — add `"section": FunnelSG.pref_section` to `_PREF_STATE_MAP`.

Add to `_build_funnel_filters` — pass `section=data.get("section")`.

Add to `build_funnel_filters` signature and body:
```python
def build_funnel_filters(
    *,
    city: str | None = None,
    rooms: str = "any",
    budget: str = "any",
    complex_name: str | None = None,
    floor: str | None = None,
    view: str | None = None,
    is_furnished: str | None = None,
    is_promotion: str | None = None,
    area: str | None = None,
    section: str | None = None,
) -> dict[str, Any]:
    # ... existing code ...
    if section and section != "any":
        filters["section"] = section
    return filters
```

Add to `get_summary_data` (after area display, ~line 425):
```python
    section_val = data.get("section")
    if section_val and section_val != "any":
        lines.append(f"📍 Секция: {section_val}")
```

Add to `on_zero_suggestion_selected` (after `rm_area`, line 928):
```python
    elif item_id == "rm_section":
        data.pop("section", None)
```

Add `"section"` to `new_search` key list (line 932-946).

Add zero suggestion in `get_results_data` (after area zero suggestion, ~line 558):
```python
                    section_v = data.get("section")
                    if section_v and section_v != "any":
                        zero_suggestions.append(("Убрать: секция " + section_v, "rm_section"))
```

**Step 5: Add Window in Dialog (after pref_complex Window)**

```python
    # Step 4g: Section sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_section",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_section_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_section_back", state=FunnelSG.preferences),
        getter=get_pref_section_options,
        state=FunnelSG.pref_section,
    ),
```

**Step 6: Run tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py -v -k "section" --timeout=10`
Expected: ALL PASS

**Step 7: Run full suite to check no regressions**

Run: `uv run pytest tests/unit/dialogs/ -n auto --dist=worksteal -v --timeout=30`
Expected: FAIL on `test_preferences_options_has_6_categories` (now 7). Fix: update test to expect 7. Also fix `test_preferences_options_uses_emoji_labels_for_all_categories` to include section.

**Step 8: Fix broken tests**

Update `test_preferences_options_has_6_categories`:
```python
async def test_preferences_options_has_7_categories():
    """Preferences getter returns 7 category items (6 original + section)."""
    result = await funnel_module.get_preferences_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    items = result["items"]
    assert len(items) == 7
```

Update `test_preferences_options_uses_emoji_labels_for_all_categories` to add:
```python
    assert labels_by_id["section"] == "📍 Секция"
```

**Step 9: Lint + full tests**

Run: `make check && uv run pytest tests/unit/ -n auto --dist=worksteal --timeout=30 -m "not legacy_api" -q`
Expected: ALL PASS

**Step 10: Commit**

```bash
git add telegram_bot/dialogs/states.py telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel.py
git commit -m "feat(funnel): add section filter with SDK Select widget and full test coverage"
```

---

## Task 6: Tests for build_funnel_filters with section

**Files:**
- Modify: `tests/unit/dialogs/test_funnel_results.py` (append)

**Step 1: Write tests**

```python
def test_section_filter():
    filters = build_funnel_filters(rooms="any", budget="any", section="D-1")
    assert filters["section"] == "D-1"


def test_section_any_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", section="any")
    assert "section" not in filters


def test_section_none_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", section=None)
    assert "section" not in filters


def test_combined_with_section():
    filters = build_funnel_filters(
        rooms="2bed", budget="high", complex_name="Premier Fort Beach", section="C-2"
    )
    assert filters["rooms"] == 3
    assert filters["section"] == "C-2"
    assert filters["complex_name"] == "Premier Fort Beach"
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel_results.py -v -k "section" --timeout=10`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/unit/dialogs/test_funnel_results.py
git commit -m "test(funnel): cover build_funnel_filters section parameter"
```

---

## Task 7: CRM integration tests + zero suggestion for section

**Files:**
- Create: `tests/unit/dialogs/test_funnel_crm_integration.py`

**Step 1: Write CRM payload tests**

```python
"""Tests for funnel → CRM integration (lead scoring payload, FSM state persistence)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import telegram_bot.dialogs.funnel as funnel_module


async def test_summary_search_calls_lead_scoring(monkeypatch):
    """on_summary_search calls _spawn_persist_funnel_lead_score with correct kwargs."""
    spawn_calls: list[dict] = []

    def fake_spawn(**kwargs: Any) -> None:
        spawn_calls.append(kwargs)

    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", fake_spawn)

    callback = MagicMock()
    callback.from_user = MagicMock(id=42)
    callback.message = MagicMock(chat=MagicMock(id=100))

    manager = SimpleNamespace(
        dialog_data={"city": "Элените", "property_type": "2bed", "budget": "high"},
        middleware_data={
            "user_service": MagicMock(),
            "pg_pool": MagicMock(),
            "lead_scoring_store": MagicMock(),
            "kommo_client": MagicMock(),
            "hot_lead_notifier": MagicMock(),
            "bot_config": MagicMock(),
        },
        switch_to=AsyncMock(),
    )

    await funnel_module.on_summary_search(callback, MagicMock(), manager)

    assert len(spawn_calls) == 1
    assert spawn_calls[0]["telegram_user_id"] == 42
    assert spawn_calls[0]["property_type"] == "2bed"
    assert spawn_calls[0]["budget"] == "high"


async def test_summary_search_stores_filters_in_fsm(monkeypatch):
    """on_summary_search stores apartment_filters in FSM state."""
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", MagicMock())

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(
        return_value=([{"id": "a1", "payload": {"complex_name": "X", "city": "Y",
                        "rooms": 1, "floor": 1, "area_m2": 40, "view_primary": "sea",
                        "price_eur": 50000}}], 1, None)
    )
    mock_bot = MagicMock()
    mock_bot._send_property_card = AsyncMock()
    mock_bot._apartments_service = mock_svc

    state_mock = MagicMock()
    state_mock.update_data = AsyncMock()

    callback = MagicMock()
    callback.from_user = MagicMock(id=1)
    callback.message = MagicMock(chat=MagicMock(id=2))
    callback.message.answer = AsyncMock()

    manager = MagicMock()
    manager.dialog_data = {"city": "Элените", "property_type": "1bed", "budget": "low"}
    manager.middleware_data = {
        "apartments_service": mock_svc,
        "property_bot": mock_bot,
        "state": state_mock,
    }
    manager.done = AsyncMock()

    await funnel_module.on_summary_search(callback, MagicMock(), manager)

    state_mock.update_data.assert_awaited_once()
    call_kwargs = state_mock.update_data.call_args[1]
    assert "apartment_filters" in call_kwargs
    assert "funnel_data" in call_kwargs
    assert call_kwargs["funnel_data"]["city"] == "Элените"


async def test_zero_suggestion_rm_section():
    """rm_section removes section and resets scroll."""
    manager = SimpleNamespace(
        dialog_data={"section": "D-1", "scroll_offset": "x", "scroll_next_offset": "y"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_section"
    )
    assert "section" not in manager.dialog_data
    assert manager.dialog_data.get("scroll_offset") is None
    manager.switch_to.assert_awaited_once_with(funnel_module.FunnelSG.results)


async def test_summary_shows_section():
    """Summary displays selected section."""
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "any", "property_type": "any", "budget": "any",
                         "section": "D-1"},
            middleware_data={},
        ),
    )
    assert "Секция: D-1" in result["summary_text"]
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel_crm_integration.py -v --timeout=10`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/unit/dialogs/test_funnel_crm_integration.py
git commit -m "test(funnel): CRM payload, FSM state persistence, section zero suggestion and summary"
```

---

## Task 8: E2E flow tests (simulated full paths)

**Files:**
- Create: `tests/unit/dialogs/test_funnel_e2e_flow.py`

**Step 1: Write flow tests**

```python
"""E2E flow tests for funnel — simulate full user paths through handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import telegram_bot.dialogs.funnel as funnel_module
from telegram_bot.dialogs.funnel import build_funnel_filters
from telegram_bot.dialogs.states import FunnelSG


async def test_full_flow_city_type_budget_done():
    """city → type → budget → pref_done → summary."""
    data: dict = {}
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    # Step 1: city
    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "Элените")
    assert data["city"] == "Элените"
    manager.switch_to.assert_awaited_with(FunnelSG.property_type)

    # Step 2: type
    manager.switch_to.reset_mock()
    await funnel_module.on_property_type_selected(
        MagicMock(), SimpleNamespace(), manager, "2bed"
    )
    assert data["property_type"] == "2bed"
    manager.switch_to.assert_awaited_with(FunnelSG.budget)

    # Step 3: budget
    manager.switch_to.reset_mock()
    await funnel_module.on_budget_selected(MagicMock(), SimpleNamespace(), manager, "high")
    assert data["budget"] == "high"
    manager.switch_to.assert_awaited_with(FunnelSG.preferences)

    # Step 4: skip preferences → done
    manager.switch_to.reset_mock()
    await funnel_module.on_pref_done(MagicMock(), SimpleNamespace(), manager)
    manager.switch_to.assert_awaited_with(FunnelSG.summary)

    # Verify filters
    filters = build_funnel_filters(
        city=data["city"], rooms=data["property_type"], budget=data["budget"]
    )
    assert filters == {
        "city": "Элените",
        "rooms": 3,
        "price_eur": {"gte": 100000, "lte": 150000},
    }


async def test_full_flow_with_preferences_and_section():
    """city → type → budget → floor + section → done → filters correct."""
    data: dict = {}
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "any")
    await funnel_module.on_property_type_selected(
        MagicMock(), SimpleNamespace(), manager, "studio"
    )
    await funnel_module.on_budget_selected(MagicMock(), SimpleNamespace(), manager, "low")

    # Preferences: floor + section
    await funnel_module.on_pref_floor_selected(MagicMock(), SimpleNamespace(), manager, "high")
    await funnel_module.on_pref_section_selected(
        MagicMock(), SimpleNamespace(), manager, "D-1"
    )
    await funnel_module.on_pref_done(MagicMock(), SimpleNamespace(), manager)

    filters = build_funnel_filters(
        city=data.get("city"),
        rooms=data.get("property_type", "any"),
        budget=data.get("budget", "any"),
        floor=data.get("floor"),
        section=data.get("section"),
    )
    assert filters == {
        "rooms": [0, 1],
        "price_eur": {"lte": 50000},
        "floor": {"gte": 4, "lte": 5},
        "section": "D-1",
    }


async def test_change_filter_flow_returns_to_summary():
    """change_filter → city → re-select → back to summary."""
    data: dict = {"city": "Элените", "property_type": "1bed", "budget": "mid"}
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    # Enter change mode
    await funnel_module.on_change_filter_selected(
        MagicMock(), SimpleNamespace(), manager, "city"
    )
    assert data["_return_to_summary"] is True
    manager.switch_to.assert_awaited_with(FunnelSG.city)

    # Re-select city → should return to summary
    manager.switch_to.reset_mock()
    await funnel_module.on_city_selected(
        MagicMock(), SimpleNamespace(), manager, "Свети Влас"
    )
    assert data["city"] == "Свети Влас"
    assert "_return_to_summary" not in data
    manager.switch_to.assert_awaited_with(FunnelSG.summary)


async def test_zero_results_recovery_removes_filter():
    """Zero results → rm_floor → results refreshed with fewer filters."""
    data: dict = {
        "city": "Элените",
        "property_type": "2bed",
        "budget": "luxury",
        "floor": "top",
        "scroll_offset": "off1",
        "scroll_next_offset": "off2",
    }
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_floor"
    )
    assert "floor" not in data
    assert data.get("scroll_offset") is None
    manager.switch_to.assert_awaited_with(FunnelSG.results)

    # Verify filters without floor
    filters = build_funnel_filters(
        city=data.get("city"),
        rooms=data.get("property_type", "any"),
        budget=data.get("budget", "any"),
        floor=data.get("floor"),
    )
    assert "floor" not in filters
    assert filters["city"] == "Элените"
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel_e2e_flow.py -v --timeout=10`
Expected: ALL PASS

**Step 3: Run full suite**

Run: `uv run pytest tests/unit/ -n auto --dist=worksteal --timeout=30 -m "not legacy_api" -q`
Expected: ALL PASS

**Step 4: Lint**

Run: `make check`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/dialogs/test_funnel_e2e_flow.py
git commit -m "test(funnel): E2E flow tests — full path, change filter, zero recovery, section"
```

---

## Task 9: Final verification

**Step 1: Required lint/type gate**

Run: `make check`
Expected: PASS

**Step 2: Required unit gate (AGENTS)**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
Expected: ALL PASS, new tests counted

**Step 3: Count new tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py tests/unit/dialogs/test_funnel_results.py tests/unit/dialogs/test_funnel_crm_integration.py tests/unit/dialogs/test_funnel_e2e_flow.py tests/unit/services/test_apartments_service.py --collect-only -q 2>/dev/null | tail -1`
Expected: ~100+ tests total in these files (existing + new)

**Step 4: Git status and final review**

Run: `git fetch --prune && git diff --stat origin/main...HEAD` to review all changes against fresh remote baseline.
