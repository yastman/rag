# Design: SDK-виджеты для карточек в funnel results

**Дата:** 2026-03-05
**Scope:** Замена кастомного `format_property_card()` на aiogram-dialog `List` + `Format` в results Window + фикс `_send_property_card`

## Проблема

1. Карточки в results Window формируются кастомной функцией `format_property_card()`, хотя весь остальной funnel уже на SDK-виджетах (Select, Format, Multiselect и т.д.)
2. В `_send_property_card()` (bot.py:1160) не передаются `section` и `apartment_number`
3. Города, комплексы, секции захардкожены в `_CITY_OPTIONS`, `_COMPLEX_OPTIONS`, `_SECTION_OPTIONS` — не берутся из данных

## Что менять

### 1. Results Window: `List` + `Format` вместо `format_property_card()`

**Было (кастом):**
```python
# get_results_data() — строит текст вручную
for apt in results:
    cards.append(format_property_card(property_id=..., complex_name=..., ...))
results_text = "\n\n".join(cards)
# Window: Format("{title}\n\n{results_text}")
```

**Стало (SDK):**
```python
# get_results_data() — возвращает список dict-ов
apartments = []
for apt in results:
    p = apt["payload"]
    apartments.append({
        "complex_name": p.get("complex_name", ""),
        "section": p.get("section", ""),
        "apartment_number": p.get("apartment_number", ""),
        "city": p.get("city", ""),
        "property_type": _ROOMS_DISPLAY.get(p.get("rooms", 1), ""),
        "floor": p.get("floor", 0),
        "area_m2": p.get("area_m2", 0),
        "view": p.get("view_primary", ""),
        "price_formatted": f'{int(p.get("price_eur", 0)):,}'.replace(",", " "),
    })
return {
    "apartments": apartments,
    "has_apartments": bool(apartments),
    ...
}

# Window — SDK List виджет
Window(
    Format("{title}"),
    List(
        Format(
            "🏠 Комплекс: {item[complex_name]}\n"
            "🏗 Секция: {item[section]}\n"
            "🚪 №: {item[apartment_number]}\n"
            "📍 Город: {item[city]}\n"
            "🛏 Тип: {item[property_type]}\n"
            "🔼 Этаж: {item[floor]}\n"
            "📐 Площадь: {item[area_m2]} м²\n"
            "🌅 Вид: {item[view]}\n"
            "💰 Цена: {item[price_formatted]} €"
        ),
        items="apartments",
        sep="\n\n",
        id="apt_list",
    ),
    Format("{no_results_text}", when="no_results"),
    ...
    state=FunnelSG.results,
)
```

**Плюсы:** Единый шаблон, section/apartment_number гарантированно в карточке, нет зависимости от `property_card.py` в funnel.

### 2. Фикс `_send_property_card()` (bot.py)

Добавить `section` и `apartment_number` в вызов `format_property_card()`:

```python
card = format_property_card(
    ...
    section=p.get("section", ""),
    apartment_number=p.get("apartment_number", ""),
)
```

Это для карточек с фото+кнопками вне dialog-а (закладки, results:more, agent). Тут SDK не применим — карточки отправляются через `message.answer()`.

### 3. Динамические опции из Qdrant (города, комплексы, секции)

**Было:** захардкожены в `_CITY_OPTIONS`, `_COMPLEX_OPTIONS`, `_SECTION_OPTIONS`.

**Стало:** getter-ы запрашивают уникальные значения из `ApartmentsService`:

```python
async def get_city_options(**kwargs):
    svc = kwargs["dialog_manager"].middleware_data.get("apartments_service")
    if svc:
        cities = await svc.get_distinct_values("city")
        items = [(c, c) for c in cities] + [("Любой город", "any")]
    else:
        items = _CITY_OPTIONS  # fallback на хардкод
    return {"items": items, ...}
```

Аналогично для комплексов и секций. Метод `get_distinct_values(field)` добавляется в `ApartmentsService` — один scroll по Qdrant с группировкой.

**Разумный подход:** fallback на хардкод если сервис недоступен. Кеширование результатов в `dialog_data` (запрос один раз за сессию funnel).

## Что НЕ менять

- **Пагинация** — оставить кастомную (`scroll_offset` + кнопка "Показать ещё"). SDK `page_size` работает для in-memory списков, а у нас серверный `scroll_with_filters()` с offset-ами
- **`_send_property_card()`** — оставить как отдельные сообщения с фото + inline-кнопками. SDK List не поддерживает per-item кнопки
- **`format_property_card()`** — не удалять, она используется в `_send_property_card()` и закладках
- **Шаги 1-5 funnel** — уже на SDK, менять не нужно

## Файлы

| Файл | Изменения |
|------|-----------|
| `telegram_bot/dialogs/funnel.py` | getter `get_results_data` → возвращает list dict-ов; Window results → `List` + `Format`; getter-ы city/complex/section → динамические |
| `telegram_bot/bot.py` | `_send_property_card()` → добавить section + apartment_number |
| `telegram_bot/services/apartments_service.py` | Добавить `get_distinct_values(field)` |
| `tests/unit/dialogs/test_funnel_results.py` | Обновить тесты под новый формат getter |
| `tests/unit/test_send_property_card.py` | Тест на section/apartment_number |

## Риски

- **`List` виджет и условные поля:** если section пустая, строка "🏗 Секция: " всё равно покажется. Решение: использовать `Case` или `Jinja` виджет вместо простого `Format` для условного рендеринга
- **`get_distinct_values` нагрузка:** кешировать в `dialog_data`, вызывать один раз при старте funnel
- **Обратная совместимость тестов:** getter теперь возвращает `apartments` list вместо `results_text` string
