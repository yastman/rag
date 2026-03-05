# Funnel SDK Cards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Заменить кастомный `format_property_card()` в funnel results на SDK-виджет `List` + `Format`, добавить динамические опции (город/комплекс/секция) из Qdrant, пофиксить `_send_property_card`.

**Architecture:** getter `get_results_data` возвращает list[dict] вместо pre-formatted string. Window results использует `List(Format(...))` с условным рендерингом через `Jinja`. Динамические опции загружаются из `ApartmentsService.get_distinct_values()` с fallback на хардкод.

**Tech Stack:** aiogram-dialog (List, Format, Jinja), qdrant-client (scroll + group_by), pytest

---

### Task 1: Фикс `_send_property_card` — добавить section/apartment_number

**Files:**
- Modify: `telegram_bot/bot.py:1160-1169`
- Modify: `tests/unit/test_send_property_card.py:54-68`

**Step 1: Обновить `_sample_result` в тесте — добавить section и apartment_number**

В `tests/unit/test_send_property_card.py` обновить фикстуру `_sample_result`:

```python
def _sample_result(property_id: str = "prop-1") -> dict:
    return {
        "id": property_id,
        "score": 0.9,
        "payload": {
            "complex_name": "Test Complex",
            "city": "Бургас",
            "property_type": "Студия",
            "floor": 2,
            "area_m2": 45,
            "view_tags": ["sea"],
            "view_primary": "sea",
            "price_eur": 55000,
            "section": "B-2",
            "apartment_number": "105",
        },
    }
```

**Step 2: Написать тест проверяющий что section и apartment_number попадают в карточку**

В `tests/unit/test_send_property_card.py` добавить тест:

```python
@patch(
    "telegram_bot.keyboards.property_card.get_demo_photo_paths",
    return_value=[Path("/tmp/demo.jpg")],
)
async def test_send_property_card_includes_section_and_apartment_number(
    _mock_photos: MagicMock,
) -> None:
    """_send_property_card includes section and apartment_number in card text."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.is_favorited = AsyncMock(return_value=False)

    message = MagicMock()
    message.answer = AsyncMock()
    message.answer_media_group = AsyncMock()

    result = _sample_result("prop-1")

    await bot._send_property_card(message, result, telegram_id=123)

    card_text = message.answer.call_args[0][0]
    assert "B-2" in card_text
    assert "105" in card_text
```

**Step 3: Запустить тест — убедиться что падает**

```bash
uv run pytest tests/unit/test_send_property_card.py::test_send_property_card_includes_section_and_apartment_number -v
```

Expected: FAIL — section и apartment_number не в тексте карточки.

**Step 4: Добавить section и apartment_number в `_send_property_card`**

В `telegram_bot/bot.py` в методе `_send_property_card`, в вызов `format_property_card()` (~строка 1160) добавить:

```python
card = format_property_card(
    property_id=result["id"],
    complex_name=p.get("complex_name", ""),
    location=p.get("city", ""),
    property_type=p.get("property_type", ""),
    floor=p.get("floor", 0),
    area_m2=p.get("area_m2", 0),
    view=", ".join(p.get("view_tags", [])) or p.get("view_primary", ""),
    price_eur=p.get("price_eur", 0),
    section=p.get("section", ""),
    apartment_number=p.get("apartment_number", ""),
)
```

**Step 5: Запустить тесты**

```bash
uv run pytest tests/unit/test_send_property_card.py -v
```

Expected: ALL PASS.

**Step 6: Коммит**

```bash
git add telegram_bot/bot.py tests/unit/test_send_property_card.py
git commit -m "fix(bot): add section and apartment_number to _send_property_card"
```

---

### Task 2: `get_distinct_values()` в ApartmentsService

**Files:**
- Modify: `telegram_bot/services/apartments_service.py`
- Create: `tests/unit/services/test_apartments_distinct.py`

**Step 1: Написать тест для `get_distinct_values`**

Создать `tests/unit/services/test_apartments_distinct.py`:

```python
"""Tests for ApartmentsService.get_distinct_values."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.apartments_service import ApartmentsService


@pytest.fixture
def svc() -> ApartmentsService:
    qdrant = MagicMock()
    qdrant.collection_name = "apartments"
    return ApartmentsService(qdrant=qdrant)


async def test_get_distinct_values_returns_sorted_unique(svc: ApartmentsService) -> None:
    """get_distinct_values returns sorted unique values for a field."""
    # Mock scroll returning records with duplicate cities
    record1 = MagicMock()
    record1.payload = {"city": "Свети Влас"}
    record1.id = "1"
    record2 = MagicMock()
    record2.payload = {"city": "Солнечный берег"}
    record2.id = "2"
    record3 = MagicMock()
    record3.payload = {"city": "Свети Влас"}  # duplicate
    record3.id = "3"

    svc._qdrant.client.scroll = AsyncMock(
        side_effect=[
            ([record1, record2, record3], None),  # first page, no next offset
        ]
    )

    result = await svc.get_distinct_values("city")
    assert result == ["Свети Влас", "Солнечный берег"]


async def test_get_distinct_values_empty_collection(svc: ApartmentsService) -> None:
    """get_distinct_values returns empty list for empty collection."""
    svc._qdrant.client.scroll = AsyncMock(return_value=([], None))

    result = await svc.get_distinct_values("city")
    assert result == []


async def test_get_distinct_values_skips_empty_strings(svc: ApartmentsService) -> None:
    """get_distinct_values skips records with empty or missing field values."""
    record1 = MagicMock()
    record1.payload = {"section": "A"}
    record1.id = "1"
    record2 = MagicMock()
    record2.payload = {"section": ""}
    record2.id = "2"
    record3 = MagicMock()
    record3.payload = {}
    record3.id = "3"

    svc._qdrant.client.scroll = AsyncMock(return_value=([record1, record2, record3], None))

    result = await svc.get_distinct_values("section")
    assert result == ["A"]
```

**Step 2: Запустить тест — убедиться что падает**

```bash
uv run pytest tests/unit/services/test_apartments_distinct.py -v
```

Expected: FAIL — `AttributeError: 'ApartmentsService' object has no attribute 'get_distinct_values'`

**Step 3: Реализовать `get_distinct_values`**

В `telegram_bot/services/apartments_service.py` добавить метод в класс `ApartmentsService`:

```python
async def get_distinct_values(self, field: str) -> list[str]:
    """Get sorted unique non-empty values for a payload field via scroll."""
    values: set[str] = set()
    offset = None
    while True:
        records, next_offset = await self._qdrant.client.scroll(
            collection_name=self._qdrant.collection_name,
            limit=1000,
            offset=offset,
            with_payload=[field],
            with_vectors=False,
        )
        for r in records:
            val = (r.payload or {}).get(field, "")
            if val:
                values.add(str(val))
        if next_offset is None:
            break
        offset = next_offset
    return sorted(values)
```

**Step 4: Запустить тесты**

```bash
uv run pytest tests/unit/services/test_apartments_distinct.py -v
```

Expected: ALL PASS.

**Step 5: Коммит**

```bash
git add telegram_bot/services/apartments_service.py tests/unit/services/test_apartments_distinct.py
git commit -m "feat(apartments): add get_distinct_values for dynamic filter options"
```

---

### Task 3: Динамические опции в getter-ах (город, комплекс, секция)

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py` (getter-ы `get_city_options`, `get_pref_complex_options`, `get_pref_section_options`)
- Modify: `tests/unit/dialogs/test_funnel.py` или создать `tests/unit/dialogs/test_funnel_dynamic_options.py`

**Step 1: Написать тест для динамических city options**

Создать `tests/unit/dialogs/test_funnel_dynamic_options.py`:

```python
"""Tests for dynamic funnel options from Qdrant."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


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

    # Должны быть города из сервиса + "Любой город"
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
    assert len(items) >= 2  # минимум 1 город + "Любой город"
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
    mock_svc.get_distinct_values = AsyncMock(
        return_value=["Crown Fort Club", "Premier Fort Beach"]
    )
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
```

**Step 2: Запустить тесты — убедиться что падают**

```bash
uv run pytest tests/unit/dialogs/test_funnel_dynamic_options.py -v
```

Expected: FAIL — getter-ы не вызывают `get_distinct_values`.

**Step 3: Обновить getter-ы в funnel.py**

Общий паттерн для всех трёх getter-ов — динамическая загрузка с fallback:

```python
async def get_city_options(**kwargs: Any) -> dict[str, Any]:
    i18n = kwargs.get("dialog_manager").middleware_data.get("i18n")
    title = i18n.get("funnel-city-title") if i18n else "Выберите город"
    btn_back = i18n.get("btn-back") if i18n else "Назад"

    svc = kwargs.get("dialog_manager").middleware_data.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            cities = await svc.get_distinct_values("city")
            items = [(c, c) for c in cities]
        except Exception:
            logger.warning("Failed to load dynamic cities, using fallback")
            items = list(_CITY_OPTIONS[:-1])  # всё кроме "Любой город"
    else:
        items = list(_CITY_OPTIONS[:-1])

    items.append(("Любой город", "any"))
    return {"title": title, "items": items, "btn_back": btn_back}
```

Аналогично для `get_pref_complex_options` (field="complex_name", fallback=`_COMPLEX_OPTIONS`) и `get_pref_section_options` (field="section", fallback=`_SECTION_OPTIONS`).

**Step 4: Запустить тесты**

```bash
uv run pytest tests/unit/dialogs/test_funnel_dynamic_options.py -v
```

Expected: ALL PASS.

**Step 5: Запустить существующие тесты funnel — regression check**

```bash
uv run pytest tests/unit/dialogs/test_funnel.py tests/unit/dialogs/test_funnel_results.py -v
```

Expected: ALL PASS.

**Step 6: Коммит**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel_dynamic_options.py
git commit -m "feat(funnel): dynamic city/complex/section options from Qdrant"
```

---

### Task 4: Results Window — `List` + `Jinja` вместо `format_property_card()`

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py` (getter `get_results_data`, Window results)
- Modify: `tests/unit/dialogs/test_funnel_results.py`

**Step 1: Обновить тест `test_get_results_data_returns_cards`**

В `tests/unit/dialogs/test_funnel_results.py` изменить тест — getter теперь возвращает `apartments` list вместо `results_text`:

```python
@pytest.mark.asyncio
async def test_get_results_data_returns_apartments_list():
    """get_results_data returns structured apartment dicts for List widget."""
    from telegram_bot.dialogs.funnel import get_results_data

    results = [
        {
            "id": "apt-1",
            "payload": {
                "complex_name": "Sunrise Complex",
                "section": "B-2",
                "apartment_number": "105",
                "rooms": 1,
                "floor": 2,
                "area_m2": 42.0,
                "view_primary": "sea",
                "price_eur": 48500,
                "city": "Свети Влас",
            },
        }
    ]
    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=(results, 297, "next-uuid"))

    manager = SimpleNamespace(
        dialog_data={"property_type": "studio", "budget": "low"},
        middleware_data={"apartments_service": mock_svc},
    )

    result = await get_results_data(dialog_manager=manager)

    # apartments — list of dicts для List виджета
    assert "apartments" in result
    assert len(result["apartments"]) == 1
    apt = result["apartments"][0]
    assert apt["complex_name"] == "Sunrise Complex"
    assert apt["section"] == "B-2"
    assert apt["apartment_number"] == "105"
    assert apt["price_formatted"] == "48 500"
    assert apt["property_type"] == "Студия"
    assert result["has_apartments"] is True
    assert result["has_more"] is True
    assert result["no_results"] is False
```

**Step 2: Написать тест для пустых результатов**

```python
@pytest.mark.asyncio
async def test_get_results_data_no_results_sets_flag():
    """get_results_data sets no_results=True when empty."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=([], 0, None))

    manager = SimpleNamespace(
        dialog_data={"property_type": "3bed", "budget": "luxury"},
        middleware_data={"apartments_service": mock_svc},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["apartments"] == []
    assert result["has_apartments"] is False
    assert result["no_results"] is True
```

**Step 3: Запустить тесты — убедиться что падают**

```bash
uv run pytest tests/unit/dialogs/test_funnel_results.py::test_get_results_data_returns_apartments_list tests/unit/dialogs/test_funnel_results.py::test_get_results_data_no_results_sets_flag -v
```

Expected: FAIL — getter возвращает `results_text` вместо `apartments`.

**Step 4: Переписать `get_results_data` — возвращать list[dict]**

В `telegram_bot/dialogs/funnel.py` изменить getter `get_results_data`. Вместо `format_property_card()` формировать list of dicts:

```python
_ROOMS_DISPLAY: dict[int, str] = {
    0: "Студия",
    1: "Студия",
    2: "1-спальня",
    3: "2-спальни",
    4: "3-спальни",
}

async def get_results_data(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for results window — returns structured data for List widget."""
    i18n = dialog_manager.middleware_data.get("i18n")
    data = dialog_manager.dialog_data

    no_results_text = (
        i18n.get("results-no-results")
        if i18n
        else "К сожалению, по вашим критериям ничего не найдено."
    )
    results_title = i18n.get("funnel-results-title") if i18n else "Результаты"
    btn_more = i18n.get("results-show-more") if i18n else "🔄 Показать ещё"
    service_unavailable_text = (
        i18n.get("results-service-unavailable") if i18n else "Сервис поиска недоступен."
    )
    btn_back = i18n.get("btn-back") if i18n else "Назад"

    apartments: list[dict[str, Any]] = []
    has_more = False
    no_results = False
    total_count = 0
    shown_start = 0
    shown_end = 0

    svc = dialog_manager.middleware_data.get("apartments_service")
    if svc is None:
        property_bot = dialog_manager.middleware_data.get("property_bot")
        if property_bot is not None:
            svc = getattr(property_bot, "_apartments_service", None)

    if svc is not None:
        try:
            filters = _build_funnel_filters(data)
            scroll_offset = data.get("scroll_offset")

            results, total_count, next_offset = await svc.scroll_with_filters(
                filters=filters,
                limit=_SCROLL_PAGE_SIZE,
                offset=scroll_offset,
            )
            data["scroll_next_offset"] = str(next_offset) if next_offset else None
            has_more = next_offset is not None

            if results:
                current_page = max(int(data.get("scroll_page", 1) or 1), 1)
                shown_start = (current_page - 1) * _SCROLL_PAGE_SIZE + 1
                shown_end = shown_start + len(results) - 1
                for apt in results:
                    p = apt["payload"]
                    rooms_num = p.get("rooms", 1)
                    apartments.append({
                        "complex_name": p.get("complex_name", ""),
                        "section": p.get("section", ""),
                        "apartment_number": p.get("apartment_number", ""),
                        "city": p.get("city", ""),
                        "property_type": _ROOMS_DISPLAY.get(rooms_num, str(rooms_num)),
                        "floor": p.get("floor", 0),
                        "area_m2": p.get("area_m2", 0),
                        "view": p.get("view_primary", ""),
                        "price_formatted": f'{int(p.get("price_eur", 0)):,}'.replace(",", " "),
                    })

                if has_more:
                    remaining = max(total_count - shown_end, 0)
                    if i18n:
                        try:
                            btn_more = i18n.get(
                                "results-show-more-remaining", remaining=remaining
                            )
                        except Exception:
                            btn_more = f"{i18n.get('results-show-more')} ({remaining} осталось)"
                    else:
                        btn_more = f"🔄 Показать ещё ({remaining} осталось)"
            else:
                no_results = True
        except Exception:
            logger.exception("Failed to fetch funnel results")
            no_results = True
            no_results_text = service_unavailable_text
    else:
        no_results = True
        no_results_text = service_unavailable_text

    # Title
    if apartments:
        if i18n:
            try:
                title = i18n.get(
                    "results-found-range",
                    total=total_count,
                    start=shown_start,
                    end=shown_end,
                )
            except Exception:
                title = f"{results_title}: {total_count}"
        else:
            title = f"Найдено {total_count} апартаментов (показаны {shown_start}–{shown_end})"
    else:
        title = results_title

    # Persist for CRM scoring
    _spawn_persist_funnel_lead_score(
        dialog_manager=dialog_manager,
        total_count=total_count,
    )

    return {
        "title": title,
        "apartments": apartments,
        "has_apartments": bool(apartments),
        "no_results": no_results,
        "no_results_text": no_results_text,
        "has_more": has_more,
        "btn_more": btn_more,
        "btn_back": btn_back,
        "zero_suggestions": [],  # TODO: сохранить zero-result suggestions если нужны
    }
```

Убрать `from telegram_bot.keyboards.property_card import format_property_card` из этой функции.

**Step 5: Обновить Window results — заменить `Format("{results_text}")` на `List` + `Jinja`**

В `telegram_bot/dialogs/funnel.py` добавить импорт:

```python
from aiogram_dialog.widgets.text import Format, Jinja, List
```

Заменить Window results (строки ~1226-1247):

```python
    # Step 6: Results (SDK List widget)
    Window(
        Format("{title}"),
        List(
            Jinja(
                "🏠 Комплекс: {{ item.complex_name }}"
                "{% if item.section %}\n🏗 Секция: {{ item.section }}{% endif %}"
                "{% if item.apartment_number %}\n🚪 №: {{ item.apartment_number }}{% endif %}"
                "{% if item.city %}\n📍 Город: {{ item.city }}{% endif %}"
                "{% if item.property_type %}\n🛏 Тип: {{ item.property_type }}{% endif %}"
                "{% if item.floor %}\n🔼 Этаж: {{ item.floor }}{% endif %}"
                "{% if item.area_m2 %}\n📐 Площадь: {{ item.area_m2 }} м²{% endif %}"
                "{% if item.view %}\n🌅 Вид: {{ item.view }}{% endif %}"
                "\n💰 Цена: {{ item.price_formatted }} €"
            ),
            items="apartments",
            sep="\n\n",
            id="apt_list",
            when="has_apartments",
        ),
        Format("{no_results_text}", when="no_results"),
        Column(
            Select(
                Format("{item[0]}"),
                id="zero_suggestions",
                item_id_getter=operator.itemgetter(1),
                items="zero_suggestions",
                on_click=on_zero_suggestion_selected,
            ),
            when="zero_suggestions",
        ),
        Button(
            Format("{btn_more}"),
            id="more",
            on_click=on_results_more,
            when="has_more",
        ),
        Cancel(Format("{btn_back}")),
        getter=get_results_data,
        state=FunnelSG.results,
    ),
```

**Step 6: Запустить тесты**

```bash
uv run pytest tests/unit/dialogs/test_funnel_results.py -v
```

Expected: Новые тесты PASS. Старые тесты нужно обновить (см. Step 7).

**Step 7: Обновить существующие тесты под новый формат**

В `tests/unit/dialogs/test_funnel_results.py`:

- `test_get_results_data_returns_cards` → переименовать/заменить на `test_get_results_data_returns_apartments_list` (Step 1)
- `test_get_results_data_no_results` → обновить assertion: `result["no_results"] is True` вместо `"ничего не найдено" in result["results_text"]`
- `test_get_results_data_no_service` → обновить: `result["no_results"] is True`
- `test_get_results_data_uses_i18n_strings` → обновить: проверять `result["title"]`, `result["btn_more"]`
- `test_get_results_data_uses_i18n_range_and_remaining_when_results_exist` → обновить: `result["apartments"]` вместо `results_text`

**Step 8: Запустить полный набор тестов**

```bash
uv run pytest tests/unit/dialogs/test_funnel.py tests/unit/dialogs/test_funnel_results.py tests/unit/dialogs/test_funnel_e2e_flow.py -v
```

Expected: ALL PASS.

**Step 9: Коммит**

```bash
git add telegram_bot/dialogs/funnel.py tests/unit/dialogs/test_funnel_results.py
git commit -m "feat(funnel): replace format_property_card with SDK List+Jinja widget"
```

---

### Task 5: Lint + type check + full regression

**Files:** Все изменённые файлы

**Step 1: Lint и types**

```bash
make check
```

Expected: ALL PASS. Если ошибки — исправить.

**Step 2: Полный unit test suite**

```bash
make test-unit
```

Expected: ALL PASS.

**Step 3: Финальный коммит (если были lint-фиксы)**

```bash
git add -u && git commit -m "style: lint fixes for funnel SDK migration"
```
