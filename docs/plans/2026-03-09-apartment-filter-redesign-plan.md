# Apartment Filter Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Переработать подбор апартаментов: упростить summary, заменить нижнее меню на навигацию каталога, добавить inline фильтр-панель, единый page size = 10, payload-only scroll.

**Architecture:** Funnel dialog (5 шагов) → dialog closes → FSMContext хранит фильтры и scroll state → ReplyKeyboard заменяется на каталог-клавиатуру → inline фильтр-панель через callback handlers с edit-in-place. Поиск через Qdrant scroll (payload filter, без vector search).

**Tech Stack:** Python 3.12, aiogram 3.x, aiogram-dialog, Qdrant (scroll + count), Redis (FSMContext)

**Design doc:** `docs/plans/2026-03-09-apartment-filter-redesign-design.md`

---

## Task 1: count_with_filters() в ApartmentsService

Добавить метод подсчёта апартаментов по фильтрам (без vector search). Используется в summary и фильтр-панели.

**Files:**
- Modify: `telegram_bot/services/apartments_service.py` (после scroll_with_filters, ~line 236)
- Test: `tests/unit/services/test_apartments_service.py`

**Step 1: Write failing test**

```python
# tests/unit/services/test_apartments_service.py

class TestCountWithFilters:
    async def test_count_no_filters_returns_total(self, mock_qdrant):
        mock_qdrant.count.return_value = SimpleNamespace(count=297)
        svc = ApartmentsService(mock_qdrant)
        result = await svc.count_with_filters(filters=None)
        assert result == 297

    async def test_count_with_city_filter(self, mock_qdrant):
        mock_qdrant.count.return_value = SimpleNamespace(count=42)
        svc = ApartmentsService(mock_qdrant)
        result = await svc.count_with_filters(filters={"city": "Солнечный берег"})
        assert result == 42
        call_args = mock_qdrant.count.call_args
        assert call_args.kwargs["count_filter"] is not None

    async def test_count_with_combined_filters(self, mock_qdrant):
        mock_qdrant.count.return_value = SimpleNamespace(count=15)
        svc = ApartmentsService(mock_qdrant)
        result = await svc.count_with_filters(
            filters={"city": "Солнечный берег", "rooms": 2, "price_eur": {"gte": 50000, "lte": 100000}}
        )
        assert result == 15
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/services/test_apartments_service.py::TestCountWithFilters -v
```
Expected: FAIL — `AttributeError: 'ApartmentsService' object has no attribute 'count_with_filters'`

**Step 3: Write implementation**

```python
# telegram_bot/services/apartments_service.py — добавить после scroll_with_filters

@observe("apartments-count")
async def count_with_filters(self, filters: dict | None = None) -> int:
    """Count apartments matching payload filters (no vector search)."""
    qdrant_filter = _build_apartment_filter(filters)
    result = await self._qdrant.count(
        collection_name="apartments",
        count_filter=qdrant_filter,
        exact=True,
    )
    return result.count
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/services/test_apartments_service.py::TestCountWithFilters -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/apartments_service.py tests/unit/services/test_apartments_service.py
git commit -m "feat(apartments): add count_with_filters for live counter"
```

---

## Task 2: build_catalog_keyboard() — ReplyKeyboard для каталога

Новая функция для нижнего меню в режиме каталога.

**Files:**
- Modify: `telegram_bot/keyboards/client_keyboard.py` (добавить функцию)
- Test: `tests/unit/keyboards/test_client_keyboard.py` (новый файл или дополнить)

**Step 1: Write failing test**

```python
# tests/unit/keyboards/test_catalog_keyboard.py

from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard


class TestBuildCatalogKeyboard:
    def test_has_4_buttons(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert len(buttons) == 4

    def test_show_more_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[0][0].text == "📥 Показать ещё 10"

    def test_counter_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[0][1].text == "10 из 47"

    def test_filters_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[1][0].text == "🔍 Фильтры"

    def test_main_menu_button(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.keyboard[1][1].text == "🏠 Главное меню"

    def test_all_shown_replaces_button(self):
        kb = build_catalog_keyboard(shown=47, total=47)
        assert kb.keyboard[0][0].text == "✅ Все 47 показаны"

    def test_resize_keyboard_true(self):
        kb = build_catalog_keyboard(shown=10, total=47)
        assert kb.resize_keyboard is True
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/keyboards/test_catalog_keyboard.py -v
```
Expected: FAIL — ImportError

**Step 3: Write implementation**

```python
# telegram_bot/keyboards/client_keyboard.py — добавить в конец файла

# --- Catalog mode keyboard ---

CATALOG_BUTTONS: dict[str, str] = {
    "📥 Показать ещё 10": "catalog_more",
    "🔍 Фильтры": "catalog_filters",
    "🏠 Главное меню": "catalog_exit",
}


def build_catalog_keyboard(*, shown: int, total: int) -> ReplyKeyboardMarkup:
    """Build ReplyKeyboard for catalog browsing mode."""
    has_more = shown < total
    more_text = "📥 Показать ещё 10" if has_more else f"✅ Все {total} показаны"
    counter_text = f"{shown} из {total}"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=more_text), KeyboardButton(text=counter_text)],
            [KeyboardButton(text="🔍 Фильтры"), KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
    )


def parse_catalog_button(text: str) -> str | None:
    """Parse catalog keyboard button text to action ID."""
    if text.startswith("📥 Показать"):
        return "catalog_more"
    if text.startswith("✅ Все"):
        return "catalog_more"  # no-op, всё показано
    return CATALOG_BUTTONS.get(text)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/keyboards/test_catalog_keyboard.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/keyboards/client_keyboard.py tests/unit/keyboards/test_catalog_keyboard.py
git commit -m "feat(keyboards): add build_catalog_keyboard for catalog browsing mode"
```

---

## Task 3: Упростить summary в funnel dialog

Убрать "Списком/Карточками", заменить на "Найти/Изменить". Добавить count() в summary.

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py` (summary window ~line 1289-1320, get_summary_data ~line 488-551)
- Test: `tests/unit/dialogs/test_funnel.py`

**Step 1: Write failing tests**

```python
# tests/unit/dialogs/test_funnel.py — добавить/заменить

class TestSummaryRedesign:
    async def test_summary_data_includes_count(self):
        """Summary должен показывать 'Найдено: X апартаментов'."""
        mock_svc = MagicMock()
        mock_svc.count_with_filters = AsyncMock(return_value=23)
        manager = SimpleNamespace(
            dialog_data={"city": "Солнечный берег", "property_type": "1bed", "budget": "mid"},
            middleware_data={"apartments_service": mock_svc},
        )
        result = await funnel_module.get_summary_data(**_getter_kwargs(manager))
        assert "23" in result["summary_text"]
        assert "Найдено" in result["summary_text"]

    async def test_summary_data_includes_sort_info(self):
        """Summary должен показывать сортировку."""
        mock_svc = MagicMock()
        mock_svc.count_with_filters = AsyncMock(return_value=10)
        manager = SimpleNamespace(
            dialog_data={"city": "any", "property_type": "any", "budget": "any"},
            middleware_data={"apartments_service": mock_svc},
        )
        result = await funnel_module.get_summary_data(**_getter_kwargs(manager))
        assert "цене" in result["summary_text"].lower()

    def test_summary_window_has_find_and_edit_buttons(self):
        """Summary должен иметь кнопки 'Найти' и 'Изменить', без 'Списком/Карточками'."""
        summary_window = None
        for window in funnel_module.funnel_dialog.windows.values():
            if window.get_state() == FunnelSG.summary:
                summary_window = window
                break
        assert summary_window is not None
        # Проверяем что есть кнопка с id="search_find"
        button_ids = _collect_widget_ids(summary_window)
        assert "search_find" in button_ids
        assert "change" in button_ids
        # Убрали "search_list" и "search_cards"
        assert "search_list" not in button_ids
        assert "search_cards" not in button_ids
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/dialogs/test_funnel.py::TestSummaryRedesign -v
```
Expected: FAIL

**Step 3: Write implementation**

Изменения в `telegram_bot/dialogs/funnel.py`:

**3a. get_summary_data (~line 488):** добавить вызов count_with_filters

```python
# В get_summary_data, после формирования summary_text:
svc = middleware_data.get("apartments_service")
count = 0
if svc is not None:
    try:
        filters = _build_funnel_filters(dialog_data)
        count = await svc.count_with_filters(filters=filters)
    except Exception:
        logger.exception("Failed to count apartments for summary")

summary_text += f"\n\nНайдено: {count} апартаментов\nСортировка: по цене ↑"
```

**3b. Summary window (~line 1289):** заменить кнопки

```python
# Было:
# Row(
#     SwitchTo(Format("📋 Списком"), id="search_list", state=FunnelSG.results, on_click=on_search_list, when="can_search"),
#     Button(Format("🏠 Карточками"), id="search_cards", on_click=on_summary_search, when="can_search"),
# ),

# Стало:
Row(
    Button(Format("🔍 Найти"), id="search_find", on_click=on_summary_search, when="can_search"),
    SwitchTo(Format("✏️ Изменить"), id="change", state=FunnelSG.change_filter),
),
```

Убрать SwitchTo "⚙️ Доп. пожелания" (дублирует "Изменить").

**Step 4: Run tests**

```bash
uv run pytest tests/unit/dialogs/test_funnel.py -v -k "summary"
```
Expected: PASS (новые тесты), проверить что старые summary тесты тоже проходят

**Step 5: Commit**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel.py
git commit -m "feat(funnel): simplify summary — Find/Edit buttons, live count"
```

---

## Task 4: on_summary_search — закрытие dialog + замена ReplyKeyboard

Рефактор handler: закрыть dialog, отправить 10 карточек, заменить ReplyKeyboard на каталог.

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py` (on_summary_search ~line 919-1019)
- Modify: `telegram_bot/bot.py` (page size constant, line 80)
- Test: `tests/unit/dialogs/test_funnel.py`

**Step 1: Write failing test**

```python
class TestOnSummarySearchRedesign:
    async def test_sends_10_cards(self):
        """on_summary_search отправляет 10 карточек (не 5)."""
        results = [_make_apartment(i) for i in range(15)]
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=(results[:10], 15, 80000.0, ["id9"]))
        # ... setup manager, property_bot mock ...
        await funnel_module.on_summary_search(callback, widget, manager)
        assert property_bot._send_property_card.await_count == 10

    async def test_sends_catalog_keyboard(self):
        """on_summary_search заменяет ReplyKeyboard на каталог."""
        # ... setup ...
        await funnel_module.on_summary_search(callback, widget, manager)
        # Последнее сообщение должно содержать catalog keyboard
        last_answer_call = callback.message.answer.call_args_list[-1]
        reply_markup = last_answer_call.kwargs.get("reply_markup")
        # Проверяем что это ReplyKeyboardMarkup (не InlineKeyboardMarkup)
        assert isinstance(reply_markup, ReplyKeyboardMarkup)
        button_texts = [btn.text for row in reply_markup.keyboard for btn in row]
        assert any("Показать ещё" in t for t in button_texts)
        assert "🏠 Главное меню" in button_texts

    async def test_stores_filters_in_fsm(self):
        """FSMContext сохраняет фильтры, offset, total для пагинации."""
        # ... setup ...
        await funnel_module.on_summary_search(callback, widget, manager)
        state_data = await state.get_data()
        assert state_data["apartment_filters"] is not None
        assert state_data["apartment_offset"] == 10
        assert state_data["apartment_total"] == 15
        assert state_data["catalog_mode"] is True
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/dialogs/test_funnel.py::TestOnSummarySearchRedesign -v
```

**Step 3: Write implementation**

Ключевые изменения в `on_summary_search`:

1. **Page size = 10** (заменить `_APARTMENT_PAGE_SIZE` в bot.py: `_APARTMENT_PAGE_SIZE = 10`)
2. **scroll_with_filters(limit=10)** вместо текущего limit
3. **Отправить catalog keyboard:**
   ```python
   from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

   catalog_kb = build_catalog_keyboard(shown=len(page), total=total_count)
   await callback.message.answer(
       f"Найдено {total_count} апартаментов (показаны 1–{len(page)})",
       reply_markup=catalog_kb,
   )
   ```
4. **FSMContext:** добавить `catalog_mode=True` для роутинга в handle_menu_button

**Step 4: Run tests**

```bash
uv run pytest tests/unit/dialogs/test_funnel.py -v -k "summary_search"
```

**Step 5: Commit**

```bash
git add telegram_bot/dialogs/funnel.py telegram_bot/bot.py tests/unit/dialogs/test_funnel.py
git commit -m "feat(funnel): send 10 cards + catalog ReplyKeyboard on search"
```

---

## Task 5: Catalog mode handler — "Показать ещё 10"

Handler для ReplyKeyboard кнопки "Показать ещё 10" в catalog mode.

**Files:**
- Modify: `telegram_bot/bot.py` (новый handler или дополнение handle_menu_button)
- Test: `tests/unit/test_catalog_handler.py` (новый файл)

**Step 1: Write failing test**

```python
# tests/unit/test_catalog_handler.py

class TestCatalogMoreHandler:
    async def test_sends_next_10_cards(self):
        """Кнопка 'Показать ещё 10' отправляет следующую пачку."""
        existing = [_make_apartment(i) for i in range(10)]
        new_page = [_make_apartment(i) for i in range(10, 20)]
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=(new_page, 30, 120000.0, ["id19"]))

        state = FSMContext(...)  # mock
        await state.update_data(
            catalog_mode=True,
            apartment_offset=10,
            apartment_total=30,
            apartment_next_offset=80000.0,
            apartment_filters={"city": "Солнечный берег"},
            apartment_scroll_seen_ids=["id9"],
        )
        # ... call handler ...
        assert property_bot._send_property_card.await_count == 10

    async def test_updates_keyboard_counter(self):
        """После отправки обновляет ReplyKeyboard с новым счётчиком."""
        # ... setup ...
        # Проверяем что keyboard обновлён: "20 из 30"
        last_call = message.answer.call_args_list[-1]
        kb = last_call.kwargs["reply_markup"]
        assert "20 из 30" in [btn.text for row in kb.keyboard for btn in row]

    async def test_all_shown_changes_button(self):
        """Когда всё показано, кнопка меняется на '✅ Все N показаны'."""
        # offset=20, total=25, new_page has 5 items
        # ... setup ...
        kb = last_call.kwargs["reply_markup"]
        assert any("✅ Все 25 показаны" in btn.text for row in kb.keyboard for btn in row)

    async def test_no_more_does_nothing(self):
        """Если всё уже показано, кнопка не отправляет ничего."""
        state = await state.update_data(apartment_offset=30, apartment_total=30)
        # ... call handler ...
        assert property_bot._send_property_card.await_count == 0
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_catalog_handler.py -v
```

**Step 3: Write implementation**

В `telegram_bot/bot.py`:

```python
async def _handle_catalog_more(self, message: Message, state: FSMContext) -> None:
    """Handle 'Показать ещё 10' in catalog mode."""
    data = await state.get_data()
    offset = data.get("apartment_offset", 0)
    total = data.get("apartment_total", 0)
    filters = data.get("apartment_filters")
    next_start = data.get("apartment_next_offset")
    seen_ids = data.get("apartment_scroll_seen_ids", [])

    if offset >= total:
        return  # всё показано

    results, total_count, new_next_start, page_ids = (
        await self._apartments_service.scroll_with_filters(
            filters=filters,
            limit=10,
            start_from=next_start,
            exclude_ids=seen_ids if next_start is not None else None,
        )
    )

    for result in results:
        await self._send_property_card(message, result, message.from_user.id)

    new_offset = offset + len(results)
    await state.update_data(
        apartment_offset=new_offset,
        apartment_total=total_count,
        apartment_next_offset=new_next_start,
        apartment_scroll_seen_ids=page_ids,
    )

    catalog_kb = build_catalog_keyboard(shown=new_offset, total=total_count)
    await message.answer(
        f"Показаны {new_offset} из {total_count} апартаментов",
        reply_markup=catalog_kb,
    )
```

Добавить роутинг в `handle_menu_button`:
```python
# В handle_menu_button, перед dispatch по action_id:
data = await state.get_data()
if data.get("catalog_mode"):
    catalog_action = parse_catalog_button(message.text)
    if catalog_action == "catalog_more":
        return await self._handle_catalog_more(message, state)
    elif catalog_action == "catalog_filters":
        return await self._handle_catalog_filters(message, state)
    elif catalog_action == "catalog_exit":
        await state.update_data(catalog_mode=False)
        await message.answer("Главное меню", reply_markup=build_client_keyboard())
        return
```

**Step 4: Run tests**

```bash
uv run pytest tests/unit/test_catalog_handler.py -v
```

**Step 5: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_catalog_handler.py
git commit -m "feat(catalog): handle 'show more 10' ReplyKeyboard button"
```

---

## Task 6: Catalog mode — "🏠 Главное меню" и "🔍 Фильтры"

Handler для выхода из каталога и кнопки фильтров.

**Files:**
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/test_catalog_handler.py`

**Step 1: Write failing test**

```python
class TestCatalogExitHandler:
    async def test_exit_restores_client_keyboard(self):
        """'Главное меню' возвращает обычный ReplyKeyboard."""
        await state.update_data(catalog_mode=True)
        # ... trigger catalog_exit ...
        assert data.get("catalog_mode") is False
        kb = message.answer.call_args.kwargs["reply_markup"]
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "🏠 Подобрать квартиру" in button_texts

    async def test_exit_clears_apartment_state(self):
        """Выход из каталога очищает apartment_* ключи FSMContext."""
        await state.update_data(
            catalog_mode=True,
            apartment_offset=20,
            apartment_results=[],
        )
        # ... trigger catalog_exit ...
        data = await state.get_data()
        assert "apartment_offset" not in data


class TestCatalogFiltersHandler:
    async def test_filters_sends_inline_panel(self):
        """'Фильтры' отправляет inline-сообщение с фильтр-панелью."""
        await state.update_data(
            catalog_mode=True,
            apartment_filters={"city": "Солнечный берег", "rooms": 2},
        )
        # ... trigger catalog_filters ...
        call = message.answer.call_args
        assert isinstance(call.kwargs["reply_markup"], InlineKeyboardMarkup)
        text = call.args[0] if call.args else call.kwargs.get("text", "")
        assert "Солнечный берег" in text
        assert "Найдено" in text
```

**Step 2-5:** Аналогично Task 5 — RED → GREEN → commit.

```bash
git commit -m "feat(catalog): exit to main menu + filter panel trigger"
```

---

## Task 7: Inline фильтр-панель — основной экран

Новый модуль: inline keyboard с кнопками фильтров + текст с текущими значениями + счётчик.

**Files:**
- Create: `telegram_bot/keyboards/filter_panel.py`
- Test: `tests/unit/keyboards/test_filter_panel.py` (новый файл)

**Step 1: Write failing test**

```python
# tests/unit/keyboards/test_filter_panel.py

from telegram_bot.keyboards.filter_panel import build_filter_panel_text, build_filter_panel_keyboard
from telegram_bot.callback_data import FilterPanelCB


class TestFilterPanelText:
    def test_shows_active_filters(self):
        text = build_filter_panel_text(
            filters={"city": "Солнечный берег", "rooms": 2},
            count=23,
        )
        assert "Солнечный берег" in text
        assert "23" in text

    def test_shows_no_filters(self):
        text = build_filter_panel_text(filters={}, count=297)
        assert "297" in text


class TestFilterPanelKeyboard:
    def test_has_9_filter_buttons(self):
        kb = build_filter_panel_keyboard()
        # 3 ряда по 3 кнопки фильтров + 3 ряда action кнопок
        filter_buttons = [
            btn for row in kb.inline_keyboard[:3] for btn in row
        ]
        assert len(filter_buttons) == 9

    def test_has_apply_button(self):
        kb = build_filter_panel_keyboard(count=23)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Применить" in t and "23" in t for t in texts)

    def test_has_reset_button(self):
        kb = build_filter_panel_keyboard()
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Сбросить" in t for t in texts)

    def test_has_back_button(self):
        kb = build_filter_panel_keyboard()
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Назад" in t for t in texts)

    def test_callback_data_prefix(self):
        kb = build_filter_panel_keyboard()
        first_btn = kb.inline_keyboard[0][0]
        assert first_btn.callback_data.startswith("fpanel:")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/keyboards/test_filter_panel.py -v
```

**Step 3: Write implementation**

```python
# telegram_bot/keyboards/filter_panel.py
"""Inline filter panel for apartment catalog — edit-in-place single message."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.callback_data import FilterPanelCB

# Display maps for human-readable filter values
_ROOMS_DISPLAY: dict[int | list, str] = {0: "Студия", 1: "Студия", 2: "1-спальня", 3: "2-спальни", 4: "3-спальни"}
_BUDGET_DISPLAY: dict[str, str] = {
    "low": "До 50 000 €", "mid": "50 000 – 100 000 €", "high": "100 000 – 150 000 €",
    "premium": "150 000 – 200 000 €", "luxury": "Более 200 000 €",
}


def build_filter_panel_text(*, filters: dict, count: int) -> str:
    """Build filter panel message text with active filters and count."""
    lines = ["🏠 Поиск апартаментов\n"]
    if filters.get("city"):
        lines.append(f"📍 Город: {filters['city']}")
    if filters.get("rooms") is not None:
        rooms = filters["rooms"]
        display = _ROOMS_DISPLAY.get(rooms, f"{rooms} комн.")
        lines.append(f"🛏 Комнаты: {display}")
    if filters.get("price_eur"):
        p = filters["price_eur"]
        if isinstance(p, dict):
            parts = []
            if p.get("gte"):
                parts.append(f"от {p['gte']:,.0f} €")
            if p.get("lte"):
                parts.append(f"до {p['lte']:,.0f} €")
            lines.append(f"💰 Бюджет: {' '.join(parts)}")
    if filters.get("view_tags"):
        lines.append(f"🌅 Вид: {', '.join(filters['view_tags'])}")
    if filters.get("floor"):
        lines.append(f"🏢 Этаж: {filters['floor']}")
    if filters.get("area_m2"):
        lines.append(f"📐 Площадь: {filters['area_m2']}")
    if filters.get("complex_name"):
        lines.append(f"🏘 Комплекс: {filters['complex_name']}")
    if filters.get("is_furnished") is not None:
        lines.append(f"🛋 Мебель: {'Да' if filters['is_furnished'] else 'Нет'}")
    if filters.get("is_promotion"):
        lines.append("🏷 Акции: Да")

    lines.append(f"\nНайдено: {count} апартаментов")
    return "\n".join(lines)


def build_filter_panel_keyboard(*, count: int = 0) -> InlineKeyboardMarkup:
    """Build inline keyboard for filter panel."""
    def _fb(label: str, field: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=label,
            callback_data=FilterPanelCB(action="select", field=field).pack(),
        )

    return InlineKeyboardMarkup(inline_keyboard=[
        [_fb("🏙 Город ▼", "city"), _fb("🛏 Комнаты ▼", "rooms"), _fb("💰 Бюджет ▼", "budget")],
        [_fb("🌅 Вид ▼", "view"), _fb("📐 Площадь ▼", "area"), _fb("🏢 Этаж ▼", "floor")],
        [_fb("🏘 Комплекс ▼", "complex"), _fb("🛋 Мебель ▼", "furnished"), _fb("🏷 Акции ▼", "promotion")],
        [InlineKeyboardButton(
            text=f"🔍 Применить ({count})",
            callback_data=FilterPanelCB(action="apply", field="").pack(),
        )],
        [InlineKeyboardButton(
            text="🗑 Сбросить фильтры",
            callback_data=FilterPanelCB(action="reset", field="").pack(),
        )],
        [InlineKeyboardButton(
            text="↩️ Назад к результатам",
            callback_data=FilterPanelCB(action="back", field="").pack(),
        )],
    ])
```

Добавить callback data:
```python
# telegram_bot/callback_data.py — добавить

class FilterPanelCB(CallbackData, prefix="fpanel"):
    """Filter panel callback data."""
    action: str  # "select", "apply", "reset", "back", "set"
    field: str   # "city", "rooms", "budget", "view", etc.
    value: str = ""  # значение при action="set"
```

**Step 4: Run tests**

```bash
uv run pytest tests/unit/keyboards/test_filter_panel.py -v
```

**Step 5: Commit**

```bash
git add telegram_bot/keyboards/filter_panel.py telegram_bot/callback_data.py tests/unit/keyboards/test_filter_panel.py
git commit -m "feat(filter-panel): inline filter panel keyboard and text builder"
```

---

## Task 8: Filter panel callback handlers

Handlers для inline кнопок фильтр-панели: выбор фильтра, apply, reset, back.

**Files:**
- Modify: `telegram_bot/bot.py` (зарегистрировать callback handlers)
- Test: `tests/unit/test_filter_panel_handlers.py` (новый файл)

**Step 1: Write failing tests**

```python
# tests/unit/test_filter_panel_handlers.py

class TestFilterPanelSelect:
    async def test_city_select_shows_city_options(self):
        """Нажатие 'Город' показывает варианты городов."""
        callback = make_callback(FilterPanelCB(action="select", field="city"))
        await bot._handle_filter_panel(callback, state, callback_data)
        # edit_text вызван с вариантами городов
        text = callback.message.edit_text.call_args.args[0]
        assert "Солнечный берег" in text

    async def test_city_set_updates_filters(self):
        """Выбор города обновляет фильтры в FSMContext."""
        callback = make_callback(FilterPanelCB(action="set", field="city", value="Солнечный берег"))
        await bot._handle_filter_panel(callback, state, callback_data)
        data = await state.get_data()
        assert data["apartment_filters"]["city"] == "Солнечный берег"


class TestFilterPanelApply:
    async def test_apply_sends_new_results(self):
        """'Применить' очищает старые результаты и отправляет новые."""
        await state.update_data(
            apartment_filters={"city": "Солнечный берег"},
            apartment_offset=20,  # был на странице 3
        )
        callback = make_callback(FilterPanelCB(action="apply", field=""))
        await bot._handle_filter_panel(callback, state, callback_data)
        # offset сброшен
        data = await state.get_data()
        assert data["apartment_offset"] == 10  # первая страница


class TestFilterPanelReset:
    async def test_reset_clears_all_filters(self):
        """'Сбросить' очищает все фильтры."""
        await state.update_data(apartment_filters={"city": "X", "rooms": 2})
        callback = make_callback(FilterPanelCB(action="reset", field=""))
        await bot._handle_filter_panel(callback, state, callback_data)
        data = await state.get_data()
        assert data["apartment_filters"] == {}


class TestFilterPanelBack:
    async def test_back_deletes_panel_message(self):
        """'Назад' удаляет сообщение с панелью."""
        callback = make_callback(FilterPanelCB(action="back", field=""))
        await bot._handle_filter_panel(callback, state, callback_data)
        callback.message.delete.assert_awaited_once()
```

**Step 2-5:** RED → GREEN → commit.

```bash
git commit -m "feat(filter-panel): callback handlers for select/apply/reset/back"
```

---

## Task 9: Filter panel — sub-menus для каждого фильтра

Edit-in-place под-меню для выбора значения каждого фильтра (город, комнаты, бюджет и т.д.).

**Files:**
- Modify: `telegram_bot/keyboards/filter_panel.py` (добавить build_filter_options_keyboard)
- Modify: `telegram_bot/bot.py` (handler для action="select")
- Test: `tests/unit/keyboards/test_filter_panel.py`

**Step 1: Write failing tests**

```python
class TestFilterOptionsKeyboard:
    def test_city_options(self):
        kb = build_filter_options_keyboard("city", current_value="Солнечный берег")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "✅ Солнечный берег" in texts
        assert "Свети Влас" in texts  # без ✅
        assert "Любой" in texts

    def test_rooms_options(self):
        kb = build_filter_options_keyboard("rooms", current_value=2)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Студия" in t for t in texts)

    def test_budget_options(self):
        kb = build_filter_options_keyboard("budget", current_value="mid")
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("✅" in t and "50 000" in t for t in texts)

    def test_back_button_present(self):
        kb = build_filter_options_keyboard("city")
        last_btn = kb.inline_keyboard[-1][0]
        assert "Назад" in last_btn.text
```

**Step 2-5:** RED → GREEN → commit.

```bash
git commit -m "feat(filter-panel): sub-menus for each filter with checkmark selection"
```

---

## Task 10: Обновить build_card_buttons — новая раскладка

Обновить кнопки карточки: убрать "Уточнить у менеджера" → "Менеджеру", порядок кнопок по дизайну.

**Files:**
- Modify: `telegram_bot/keyboards/property_card.py` (build_card_buttons, ~line 84-116)
- Test: `tests/unit/keyboards/test_property_card.py`

**Step 1: Write failing test**

```python
class TestCardButtonsRedesign:
    def test_button_layout_2_plus_1(self):
        """Раскладка: [В избранное][Менеджеру] + [На осмотр]."""
        kb = build_card_buttons("apt-1")
        assert len(kb.inline_keyboard) == 2
        assert len(kb.inline_keyboard[0]) == 2  # избранное + менеджер
        assert len(kb.inline_keyboard[1]) == 1  # осмотр

    def test_first_row_favorite_then_manager(self):
        kb = build_card_buttons("apt-1")
        assert "В избранное" in kb.inline_keyboard[0][0].text
        assert "Менеджеру" in kb.inline_keyboard[0][1].text

    def test_second_row_viewing(self):
        kb = build_card_buttons("apt-1")
        assert "На осмотр" in kb.inline_keyboard[1][0].text
```

**Step 2-5:** RED → GREEN → commit.

```bash
git commit -m "feat(property-card): update button layout — favorite+manager, viewing"
```

---

## Task 11: Убрать build_results_footer и старый handle_results_callback

Удалить неиспользуемый код: inline footer и старый pagination handler.

**Files:**
- Modify: `telegram_bot/keyboards/property_card.py` (удалить build_results_footer)
- Modify: `telegram_bot/bot.py` (удалить/рефакторить handle_results_callback)
- Modify: `telegram_bot/callback_data.py` (ResultsCB можно оставить для backward compat)
- Test: обновить тесты, удалить тесты на build_results_footer

**Step 1: Write failing test**

```python
class TestOldFooterRemoved:
    def test_build_results_footer_not_exported(self):
        """build_results_footer удалён из property_card."""
        assert not hasattr(property_card_module, "build_results_footer")
```

**Step 2-5:** RED → GREEN → commit. Удалить функцию, обновить imports, убрать тесты на неё.

```bash
git commit -m "refactor: remove build_results_footer and old inline pagination"
```

---

## Task 12: Удалить FunnelSG.results window и "Списком" mode

Убрать results window из dialog (результаты теперь вне dialog), убрать on_search_list.

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py` (удалить results window, on_search_list, get_results_data)
- Modify: `telegram_bot/dialogs/states.py` (оставить FunnelSG.results для backward compat или удалить)
- Test: обновить тесты

**Step 1:** Удалить results window из Dialog(), on_search_list handler, get_results_data getter.
**Step 2:** Обновить тесты — удалить тесты на results window, on_results_more.
**Step 3:** Проверить что funnel dialog по-прежнему работает (city → type → budget → prefs → summary).

```bash
git commit -m "refactor(funnel): remove results window — results now outside dialog"
```

---

## Task 13: Интеграционная проверка полного flow

Прогнать все тесты, проверить что ничего не сломано.

**Step 1: Lint + types**

```bash
make check
```
Expected: PASS

**Step 2: Unit tests**

```bash
uv run pytest tests/unit/ -n auto -v
```
Expected: PASS (с учётом удалённых/обновлённых тестов)

**Step 3: Commit финальный**

```bash
git commit -m "test: update tests for apartment filter redesign"
```

---

## Порядок выполнения и зависимости

```
Task 1 (count_with_filters)        ← независимый
Task 2 (build_catalog_keyboard)    ← независимый
Task 7 (filter_panel.py)           ← независимый

Task 3 (simplify summary)          ← зависит от Task 1
Task 10 (card buttons)             ← независимый

Task 4 (on_summary_search)         ← зависит от Task 2, 3
Task 5 (catalog_more handler)      ← зависит от Task 2, 4
Task 6 (catalog exit + filters)    ← зависит от Task 5

Task 8 (filter panel handlers)     ← зависит от Task 7
Task 9 (filter sub-menus)          ← зависит от Task 8

Task 11 (remove old footer)        ← зависит от Task 5
Task 12 (remove results window)    ← зависит от Task 4

Task 13 (integration check)        ← зависит от всех
```

**Параллельные группы:**
- **Группа A** (Tasks 1, 3, 4, 5, 6, 11, 12) — funnel + catalog mode
- **Группа B** (Tasks 7, 8, 9) — filter panel
- **Группа C** (Tasks 2, 10) — keyboards

Группы A, B, C можно разрабатывать параллельно в worktrees.
