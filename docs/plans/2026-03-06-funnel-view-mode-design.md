# Funnel View Mode: List vs Cards — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить выбор формата результатов (список / карточки) в summary Window воронки подбора апартаментов.

**Architecture:** Заменить одну кнопку "🔍 Показать результаты" на `Row(SwitchTo + Button)` в summary Window. SwitchTo → существующий SDK List Window, Button → существующий bot path с фото-карточками. Без новых State/Window.

**Tech Stack:** Python 3.12, aiogram-dialog (SwitchTo, Button, Row), pytest

---

### Task 1: Add `on_search_list` callback + `Row` import

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py:21` (import), `telegram_bot/dialogs/funnel.py:873` (near on_summary_search)
- Test: `tests/unit/dialogs/test_funnel.py`

**Step 1: Write failing test**

Add to `tests/unit/dialogs/test_funnel.py`:

```python
@pytest.mark.asyncio
async def test_on_search_list_resets_pagination():
    """on_search_list must reset scroll state before switching to list view."""
    manager = SimpleNamespace(
        dialog_data={
            "scroll_offset": "some-offset",
            "scroll_next_offset": "next",
            "scroll_page": 3,
            "city": "Бургас",
        },
    )
    callback = AsyncMock()
    await funnel_module.on_search_list(callback, None, manager)

    assert "scroll_offset" not in manager.dialog_data
    assert "scroll_next_offset" not in manager.dialog_data
    assert manager.dialog_data["scroll_page"] == 1
    # Preserve other data
    assert manager.dialog_data["city"] == "Бургас"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py::test_on_search_list_resets_pagination -v`
Expected: FAIL — `AttributeError: module has no attribute 'on_search_list'`

**Step 3: Implement `on_search_list` + add `Row` import**

In `telegram_bot/dialogs/funnel.py`, add `Row` to imports (line ~21):

```python
from aiogram_dialog.widgets.kbd import (
    Back,
    Button,
    Cancel,
    Column,
    ManagedMultiselect,
    Multiselect,
    Row,
    Select,
    SwitchTo,
)
```

Add `on_search_list` callback near `on_summary_search` (before it, around line 870):

```python
async def on_search_list(
    callback: CallbackQuery,
    widget: Any,
    manager: DialogManager,
) -> None:
    """Reset pagination before switching to list results."""
    data = manager.dialog_data
    data.pop("scroll_offset", None)
    data.pop("scroll_next_offset", None)
    data["scroll_page"] = 1
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py::test_on_search_list_resets_pagination -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel.py
git commit -m "feat(funnel): add on_search_list callback and Row import"
```

---

### Task 2: Replace summary Window button with Row(SwitchTo + Button)

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py:1247-1252` (summary Window)
- Test: `tests/unit/dialogs/test_funnel.py`

**Step 1: Write failing test**

Add to `tests/unit/dialogs/test_funnel.py`:

```python
def test_summary_window_has_list_and_cards_buttons():
    """Summary Window must have both 'list' and 'cards' result buttons."""
    from telegram_bot.dialogs.funnel import funnel_dialog

    # Find summary window (FunnelSG.summary state)
    summary_window = None
    for window in funnel_dialog.windows.values():
        if window.get_state() == FunnelSG.summary:
            summary_window = window
            break

    assert summary_window is not None, "Summary window not found"

    # Collect all button IDs recursively
    button_ids = set()

    def _collect_ids(widget):
        if hasattr(widget, "widget_id") and widget.widget_id:
            button_ids.add(widget.widget_id)
        # Row, Column, Group have .buttons
        for child in getattr(widget, "buttons", []):
            _collect_ids(child)

    for child in summary_window.keyboard.buttons:
        _collect_ids(child)

    assert "search_list" in button_ids, "Missing 'search_list' SwitchTo button"
    assert "search_cards" in button_ids, "Missing 'search_cards' Button"
    # Old single button should be gone
    assert "search" not in button_ids, "Old 'search' button still present"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py::test_summary_window_has_list_and_cards_buttons -v`
Expected: FAIL — `"search_list" not in button_ids`

**Step 3: Replace Button with Row in summary Window**

In `telegram_bot/dialogs/funnel.py`, replace the summary Window's search button (around line 1247-1252):

**Replace:**
```python
        Button(
            Format("🔍 Показать результаты"),
            id="search",
            on_click=on_summary_search,
            when="can_search",
        ),
```

**With:**
```python
        Row(
            SwitchTo(
                Format("📋 Списком"),
                id="search_list",
                state=FunnelSG.results,
                on_click=on_search_list,
                when="can_search",
            ),
            Button(
                Format("🏠 Карточками"),
                id="search_cards",
                on_click=on_summary_search,
                when="can_search",
            ),
        ),
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py::test_summary_window_has_list_and_cards_buttons -v`
Expected: PASS

**Step 5: Run all funnel tests**

Run: `uv run pytest tests/unit/dialogs/test_funnel.py tests/unit/dialogs/test_funnel_results.py -v`
Expected: all PASS

**Step 6: Run full checks**

Run: `make check && uv run pytest tests/unit/ -n auto -q --timeout=30`
Expected: 0 errors, all tests PASS

**Step 7: Commit**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel.py
git commit -m "feat(funnel): add list/cards view mode buttons to summary

Replace single 'Показать результаты' button with Row containing
'📋 Списком' (SwitchTo → SDK List) and '🏠 Карточками' (Button → bot path cards)."
```

---

## Summary of changes

| File | Change |
|------|--------|
| `telegram_bot/dialogs/funnel.py` | Add `Row` import, `on_search_list` callback, replace Button → Row(SwitchTo + Button) |
| `tests/unit/dialogs/test_funnel.py` | 2 new tests: pagination reset + button structure |

## Commit sequence

1. `feat(funnel): add on_search_list callback and Row import`
2. `feat(funnel): add list/cards view mode buttons to summary`
