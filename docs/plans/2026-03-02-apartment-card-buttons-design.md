# Apartment Card Buttons — Design

## Проблема

При подборе апартаментов бот отправляет карточки с единственной кнопкой "В закладки".
Пользователю не хватает действий прямо из карточки: записаться на осмотр, задать вопрос менеджеру,
убрать из избранного без перехода в отдельное меню.

## Решение

Расширить inline-кнопки каждой карточки до 3 действий в layout 2+1:

```
┌─────────────────────────────────┐
│ 🏠 Premier Fort, Солнечный Берег │
│ 2-комн. · 3 этаж · 65 м² · море  │
│ 💰 85 000 €                       │
├────────────────┬────────────────┤
│ 📅 На осмотр  │ 📌 В избранное │
│               │  (или ❌ Убрать) │
├────────────────┴────────────────┤
│ 💬 Уточнить у менеджера         │
└─────────────────────────────────┘
```

### Кнопки

| Кнопка | Callback | Действие |
|--------|----------|----------|
| 📅 На осмотр | `card:viewing:{property_id}` | `start_phone_collection(service_key="viewing", viewing_objects=[...])` |
| 📌 В избранное | `fav:add:{property_id}` | Добавить + `edit_reply_markup` → toggle на "Убрать" |
| ❌ Убрать из избранного | `fav:remove:{property_id}` | Удалить + `edit_reply_markup` → toggle на "В избранное" |
| 💬 Уточнить у менеджера | `card:ask:{property_id}` | `start_phone_collection(service_key="manager_question", viewing_objects=[...])` |

### Toggle избранного

- При отрисовке карточки: `is_favorited = await favorites_service.is_favorited(telegram_id, property_id)`
- При `fav:add` — callback.answer("Добавлено") + `edit_reply_markup` с `is_favorited=True`
- При `fav:remove` из результатов поиска — `edit_reply_markup` с `is_favorited=False` (не удалять сообщение)
- При `fav:remove` из раздела "Мои закладки" — удалить сообщение (текущее поведение)
- **Race condition:** `edit_reply_markup` обёрнут в `try/except` на `MessageNotModified` (быстрый двойной тап)

### DRY: хелпер `send_property_card()`

Сейчас один и тот же блок (is_favorited → format_property_card → build_card_buttons → message.answer)
дублируется в **3 местах** bot.py (строки 1553-1566, 1354-1369, 1096-1122).
Вынести в хелпер для устранения рассинхрона:

```python
async def _send_property_card(
    self,
    message: Message,
    result: dict,
    telegram_id: int,
) -> None:
    """Send a single property card with buttons (DRY helper)."""
```

## Изменяемые файлы

| Файл | Что меняется |
|------|-------------|
| `telegram_bot/keyboards/property_card.py` | `build_card_buttons(property_id, is_favorited=False)` — 2 строки кнопок, toggle текст |
| `telegram_bot/bot.py` — новый хелпер `_send_property_card()` | Единая точка отправки карточки с кнопками (заменяет 3 копипасты) |
| `telegram_bot/bot.py` — `_handle_apartment_fast_path` (L1553) | Заменить inline-код на `_send_property_card()` |
| `telegram_bot/bot.py` — `handle_results_callback` results:more (L1354) | Заменить inline-код на `_send_property_card()` |
| `telegram_bot/bot.py` — `_handle_bookmarks` (L1096) | Заменить inline-код на `_send_property_card()` |
| `telegram_bot/bot.py` — `handle_favorite_callback` | fav:add → `edit_reply_markup` + `MessageNotModified` guard; fav:remove → toggle или delete |
| `telegram_bot/bot.py` — `_register_handlers` (L642) | Добавить `self.dp.callback_query(F.data.startswith("card:"))(self.handle_card_callback)` |
| `telegram_bot/bot.py` — новый `handle_card_callback` | `card:viewing:{id}`, `card:ask:{id}` → `start_phone_collection` с property context |
| `telegram_bot/config/services.yaml` | Добавить `entry_points.manager_question` (crm_title, phone_prompt, phone_success) |
| `tests/unit/keyboards/test_property_card.py` | Тесты на новый layout `build_card_buttons` |
| `tests/unit/test_favorites_callbacks.py` | Тесты на toggle + `MessageNotModified` guard |

## CRM контекст для card:ask

При `card:ask:{property_id}` — property_id и данные объекта передаются в `viewing_objects`,
чтобы `_build_note_text()` в phone_collector записала их в CRM note.
Менеджер увидит: "Вопрос по апартаменту — Premier Fort, Студия 55м², €85,000 (ID: prop-42)".

## Не меняется

- `FavoritesService` — уже имеет `add`, `remove`, `is_favorited`
- `start_phone_collection` — уже принимает `service_key` и `viewing_objects`
- `_build_note_text()` — уже форматирует `viewing_objects` в CRM note
- `format_property_card` — текст карточки остаётся прежним
- `build_results_footer` — footer после всех карточек остаётся
- Callback prefixes `fav:add`, `fav:remove` — обратно совместимы
