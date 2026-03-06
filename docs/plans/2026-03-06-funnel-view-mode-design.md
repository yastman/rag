# Funnel View Mode: List vs Cards — Design

## Problem

Пользователь проходит воронку подбора апартаментов (funnel), но не может выбрать формат результатов.
Сейчас кнопка "🔍 Показать результаты" в summary Window вызывает `on_summary_search` — закрывает диалог и шлёт фото-карточки через bot path.

## Solution

Заменить одну кнопку "🔍 Показать результаты" на две в summary Window:
- **"📋 Показать списком"** → `SwitchTo(FunnelSG.results)` — текущий SDK Window (`List` + `Jinja`)
- **"🏠 Показать карточками"** → `Button(on_click=on_summary_search)` — текущий bot path (фото + карточки)

Чисто SDK решение: `SwitchTo` + `Button`. Новых State/Window не нужно.

## Current Flow

```
Step 5: summary Window (FunnelSG.summary)
  ├── [🔍 Показать результаты]  → on_summary_search (Button + on_click)
  ├── [✏️ Изменить параметры]   → SwitchTo(FunnelSG.change_filter)
  ├── [⚙️ Доп. пожелания]      → SwitchTo(FunnelSG.preferences)
  └── [Отмена]                  → Cancel
```

## New Flow

```
Step 5: summary Window (FunnelSG.summary)
  ├── [📋 Показать списком]     → SwitchTo(FunnelSG.results)     ← SDK List Window
  ├── [🏠 Показать карточками]  → on_summary_search (Button)     ← bot path cards
  ├── [✏️ Изменить параметры]   → SwitchTo(FunnelSG.change_filter)
  ├── [⚙️ Доп. пожелания]      → SwitchTo(FunnelSG.preferences)
  └── [Отмена]                  → Cancel
```

## Changes

### 1. `telegram_bot/dialogs/states.py` — без изменений

Новые State не нужны. `FunnelSG.results` уже существует.

### 2. `telegram_bot/dialogs/funnel.py` — summary Window

**Было (line ~1247):**
```python
Button(
    Format("🔍 Показать результаты"),
    id="search",
    on_click=on_summary_search,
    when="can_search",
),
```

**Стало:**
```python
Row(
    SwitchTo(
        Format("📋 Списком"),
        id="search_list",
        state=FunnelSG.results,
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

`Row` — SDK виджет, ставит 2 кнопки в одну строку. `when="can_search"` сохраняется для обеих.

### 3. `telegram_bot/dialogs/funnel.py` — results getter

Текущий `get_results_data()` уже делает поиск через `svc.scroll_with_filters()`.
При `SwitchTo` → results Window, getter вызывается автоматически aiogram-dialog.

Нужно убедиться что `scroll_offset` / `scroll_page` сбрасываются.
Добавить `on_click` callback к `SwitchTo` (или использовать `pre_update` в Window)
для сброса пагинации — аналогично тому что делает `on_summary_search`:

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

И прицепить к SwitchTo: `SwitchTo(..., on_click=on_search_list)`.

### 4. Import `Row` в funnel.py

Добавить `Row` в импорт aiogram-dialog виджетов (если ещё нет).

## Files

| File | Change |
|------|--------|
| `telegram_bot/dialogs/funnel.py` | Summary Window: replace 1 Button → Row(SwitchTo + Button) + on_search_list callback |
| `tests/unit/dialogs/test_funnel.py` | Тест: summary Window содержит 2 кнопки результатов |

## UX

Пользователь на экране summary видит свои параметры и два варианта:
```
Ваши параметры поиска:
📍 Город: Бургас
🛏 Тип: 1-спальня
💰 Бюджет: до 80 000€

[📋 Списком] [🏠 Карточками]
[✏️ Изменить параметры]
[⚙️ Доп. пожелания]
[Отмена]
```

- "📋 Списком" — остаётся в диалоге, видит компактный список с пагинацией
- "🏠 Карточками" — диалог закрывается, получает фото-карточки с кнопками "В избранное" / "На осмотр"

## Out of Scope

- Запоминание предпочтения пользователя (будущее)
- Переключение вида после показа результатов
- Карточки внутри aiogram-dialog (нет SDK-способа слать album)
