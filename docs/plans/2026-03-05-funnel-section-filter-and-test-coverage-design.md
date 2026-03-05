# Фильтр секции в funnel + полное покрытие тестами

**Дата:** 2026-03-05
**Статус:** Design (awaiting approval)
**Scope:** telegram_bot/dialogs/funnel.py, telegram_bot/services/, tests/unit/dialogs/

---

## 1. Контекст

Funnel подбора квартир (aiogram-dialog, 12 окон) работает, но:
- Фильтр по **секции** не реализован, хотя индекс `section: keyword` в Qdrant есть
- **~50 сценариев** не покрыты тестами (back-навигация, пагинация, CRM payload, view handler)
- Часть кнопок реализована через `Button + on_click(switch_to)` вместо SDK-виджета `SwitchTo`

## 2. Цели

1. Добавить фильтр по секции в funnel (SDK Select)
2. Заменить кастомные Button+handler на `SwitchTo` где возможно
3. Покрыть тестами **все** пробелы в пайплайне подбора квартир

## 3. Ограничения

- Без breaking changes — существующие 350+ тестов должны проходить
- Только SDK-виджеты aiogram-dialog (Select, SwitchTo, Back)
- `_build_apartment_filter()` автоматически обрабатывает `{"section": "D-1"}` через `MatchValue` — менять Qdrant-слой не нужно
- Серверную пагинацию (Qdrant scroll) на `ScrollingGroup` не заменяем — разные абстракции

---

## 4. Блок A: Фильтр секции

### 4.1 Данные

CSV колонка `section` содержит значения: `A`, `B-1`..`B-6`, `C-1`..`C-5`, `D-1`..`D-3`, `E-1`..`E-2`, `F-1`..`F-3`.
Qdrant индекс `section: keyword` уже создан.

### 4.2 Изменения

| Файл | Что меняем |
|------|-----------|
| `dialogs/states.py` | Добавить `pref_section = State()` в `FunnelSG` |
| `dialogs/funnel.py` | + `_SECTION_OPTIONS` (динамический или статический список) |
| `dialogs/funnel.py` | + getter `get_pref_section_options()` |
| `dialogs/funnel.py` | + handler `on_pref_section_selected()` |
| `dialogs/funnel.py` | + Window для `pref_section` (Select + SwitchTo back) |
| `dialogs/funnel.py` | + `("📍 Секция", "section")` в `_PREF_ITEMS` |
| `dialogs/funnel.py` | + routing `"section"` в `on_pref_category_selected()` |
| `dialogs/funnel.py` | + `section` в `_compute_active_pref_categories()` |
| `dialogs/funnel.py` | + `section` в `build_funnel_filters()` |
| `dialogs/funnel.py` | + `section` в `get_summary_data()` |
| `dialogs/funnel.py` | + `section` в `on_zero_suggestion_selected()` (rm_section) |

### 4.3 Получение списка секций

**Подход A (статический):** Захардкодить `_SECTION_OPTIONS` из CSV.
**Подход B (динамический):** Фильтровать секции по выбранному комплексу из Qdrant.

**Рекомендация:** Подход A — статический. Причины:
- Секции привязаны к комплексам, но 297 rows — список стабильный
- Динамический запрос в Qdrant из getter усложняет и замедляет
- Можно отфильтровать клиентски по `complex_name` если выбран

### 4.4 Qdrant фильтр

Никаких изменений. `_build_apartment_filter()` уже обрабатывает:
```python
{"section": "D-1"}  # → FieldCondition(key="section", match=MatchValue(value="D-1"))
```
Согласно оф. документации Qdrant: keyword exact match через `MatchValue`.

---

## 5. Блок B: SDK рефакторинг (SwitchTo)

### 5.1 Текущее состояние

6 sub-option Windows используют `Button(back, on_click=on_pref_back_to_menu)` — кастомный handler который просто делает `switch_to(FunnelSG.preferences)`.

Summary использует 3 кнопки с `Button(on_click=handler)` где handler тоже просто `switch_to`.

### 5.2 Замены

| Сейчас | SDK замена | Удаляемый handler |
|--------|-----------|-------------------|
| `Button(back, id="pref_floor_back", on_click=on_pref_back_to_menu)` | `SwitchTo(Format(btn_back), id="pref_floor_back", state=FunnelSG.preferences)` | — |
| `Button(back, id="pref_view_back", on_click=on_pref_back_to_menu)` | `SwitchTo(...)` | — |
| `Button(back, id="pref_furn_back", on_click=on_pref_back_to_menu)` | `SwitchTo(...)` | — |
| `Button(back, id="pref_promo_back", on_click=on_pref_back_to_menu)` | `SwitchTo(...)` | — |
| `Button(back, id="pref_area_back", on_click=on_pref_back_to_menu)` | `SwitchTo(...)` | — |
| `Button(back, id="pref_cplx_back", on_click=on_pref_back_to_menu)` | `SwitchTo(...)` | — |
| `Button("Изменить параметры", on_click=on_summary_change)` | `SwitchTo(..., state=FunnelSG.change_filter)` | `on_summary_change` |
| `Button("Доп. пожелания", on_click=on_summary_refine)` | `SwitchTo(..., state=FunnelSG.preferences)` | `on_summary_refine` |

**НЕ заменяем:**
- `Button("Показать результаты", on_click=on_summary_search)` — handler содержит бизнес-логику (lead scoring, search, cards)
- `Button("Нет, перейти к результатам", on_click=on_pref_done)` — можно заменить на `SwitchTo`, но handler тривиален

**Итог:** удаляем `on_pref_back_to_menu`, `on_summary_change`, `on_summary_refine` (3 handler'а).

---

## 6. Блок C: Тесты — полное покрытие

### 6.1 Уровень 1: Unit тесты funnel handlers

**Файл:** `tests/unit/dialogs/test_funnel.py` (дополнение)

#### Back-навигация (высокий приоритет)
| # | Тест | Проверяет |
|---|------|-----------|
| 1 | `test_pref_back_to_menu_switches_to_preferences` | `on_pref_back_to_menu` → `FunnelSG.preferences` |
| 2 | `test_switchto_back_in_pref_floor_targets_preferences` | SwitchTo виджет в pref_floor → state=preferences |
| 3 | `test_switchto_back_in_pref_view_targets_preferences` | Аналогично для view |
| 4 | `test_switchto_back_in_pref_section_targets_preferences` | Для нового section |

#### Пагинация results (высокий приоритет)
| # | Тест | Проверяет |
|---|------|-----------|
| 5 | `test_results_more_increments_page_and_offset` | scroll_page +1, scroll_offset = next |
| 6 | `test_results_more_no_next_offset_answers_all_shown` | next_offset=None → callback.answer("Все показаны") |

#### pref_view handler (средний приоритет)
| # | Тест | Проверяет |
|---|------|-----------|
| 7 | `test_pref_view_selected_saves_and_returns` | dialog_data["view"] = "sea", switch_to preferences |
| 8 | `test_pref_view_any_clears_value` | "any" → dialog_data["view"] is None |
| 9 | `test_pref_category_view_switches_to_pref_view` | category "view" → FunnelSG.pref_view |
| 10 | `test_pref_category_furnished_switches_to_pref_furnished` | "furnished" → FunnelSG.pref_furnished |
| 11 | `test_pref_category_promotion_switches_to_pref_promotion` | "promotion" → FunnelSG.pref_promotion |

#### Секция (новый фильтр)
| # | Тест | Проверяет |
|---|------|-----------|
| 12 | `test_pref_section_options_has_sections_plus_any` | Getter возвращает секции + "any" |
| 13 | `test_pref_section_selected_saves_and_returns` | dialog_data["section"] = "D-1" |
| 14 | `test_pref_section_any_clears_value` | "any" → None |
| 15 | `test_pref_category_section_switches_to_pref_section` | "section" → FunnelSG.pref_section |
| 16 | `test_preferences_options_has_7_categories` | items = 7 (6 + section) |
| 17 | `test_preferences_section_syncs_widget_state` | section set → checked in widget_data |

#### Zero suggestions (дополнение)
| # | Тест | Проверяет |
|---|------|-----------|
| 18 | `test_zero_suggestion_rm_view` | Убирает view, сбрасывает scroll |
| 19 | `test_zero_suggestion_rm_furnished` | Убирает is_furnished |
| 20 | `test_zero_suggestion_rm_promotion` | Убирает is_promotion |
| 21 | `test_zero_suggestion_rm_budget` | budget → "any" |
| 22 | `test_zero_suggestion_rm_section` | Убирает section (новое) |

#### Summary display (дополнение)
| # | Тест | Проверяет |
|---|------|-----------|
| 23 | `test_summary_shows_furnished_yes` | "С мебелью" в summary_text |
| 24 | `test_summary_shows_furnished_no` | "Без мебели" в summary_text |
| 25 | `test_summary_shows_promotion` | "Только акции" в summary_text |
| 26 | `test_summary_shows_section` | "Секция: D-1" в summary_text (новое) |

#### property_type return_to_summary
| # | Тест | Проверяет |
|---|------|-----------|
| 27 | `test_property_type_return_to_summary` | _return_to_summary → switch_to summary |

#### Getter контент
| # | Тест | Проверяет |
|---|------|-----------|
| 28 | `test_pref_floor_options_has_4_plus_any` | 5 items, правильные ключи |
| 29 | `test_pref_view_options_has_4_plus_any` | 5 items |
| 30 | `test_pref_furnished_options_has_3` | yes/no/any |
| 31 | `test_pref_promotion_options_has_2` | yes/any |

### 6.2 Уровень 2: Unit тесты build_funnel_filters

**Файл:** `tests/unit/dialogs/test_funnel_results.py` (дополнение)

| # | Тест | Проверяет |
|---|------|-----------|
| 32 | `test_section_filter` | section="D-1" → filters["section"] = "D-1" |
| 33 | `test_section_any_not_included` | section="any" → "section" not in filters |
| 34 | `test_section_none_not_included` | section=None → "section" not in filters |

### 6.3 Уровень 3: Unit тесты _build_apartment_filter (Qdrant)

**Файл:** `tests/unit/services/test_apartments_service.py` (дополнение/проверка)

| # | Тест | Проверяет |
|---|------|-----------|
| 35 | `test_filter_keyword_exact_match` | `{"section": "D-1"}` → `MatchValue("D-1")` |
| 36 | `test_filter_list_match_any` | `{"view_tags": ["sea","pool"]}` → `MatchAny(["sea","pool"])` |
| 37 | `test_filter_range` | `{"price_eur": {"gte":100k,"lte":200k}}` → `Range(gte=100k,lte=200k)` |
| 38 | `test_filter_bool_before_int` | `{"is_furnished": True}` → `MatchValue(True)`, не int |
| 39 | `test_filter_combined_must` | 3 фильтра → `Filter(must=[3 conditions])` |
| 40 | `test_filter_empty_returns_none` | `{}` → None |
| 41 | `test_filter_none_returns_none` | None → None |

### 6.4 Уровень 4: Integration — CRM payload

**Файл:** `tests/unit/dialogs/test_funnel_crm_integration.py` (новый)

| # | Тест | Проверяет |
|---|------|-----------|
| 42 | `test_summary_search_calls_lead_scoring` | `_spawn_persist_funnel_lead_score` вызывается с правильными kwargs |
| 43 | `test_summary_search_passes_property_type_to_scoring` | property_type из dialog_data → scoring |
| 44 | `test_summary_search_passes_budget_to_scoring` | budget из dialog_data → scoring |
| 45 | `test_summary_search_stores_filters_in_fsm` | state.update_data(apartment_filters=filters) |
| 46 | `test_summary_search_stores_funnel_data_in_fsm` | state.update_data(funnel_data=dict(data)) |

### 6.5 Уровень 5: Integration — полный путь

**Файл:** `tests/unit/dialogs/test_funnel_e2e_flow.py` (новый)

| # | Тест | Проверяет |
|---|------|-----------|
| 47 | `test_full_flow_city_type_budget_summary_search` | Симуляция полного прохода: save city → save type → save budget → pref_done → search |
| 48 | `test_full_flow_with_preferences` | + floor + view → summary → search с правильными фильтрами |
| 49 | `test_change_filter_flow_city_returns_to_summary` | change → city → save → back to summary |
| 50 | `test_zero_results_recovery_rm_filter_refreshes` | zero → rm_floor → results with fewer filters |

### 6.6 Уровень 6: Dialog structure (новый фильтр)

| # | Тест | Проверяет |
|---|------|-----------|
| 51 | `test_funnel_has_pref_section_window` | FunnelSG.pref_section в windows |
| 52 | `test_change_filter_includes_section` | section в change_filter options (если добавим) |

---

## 7. Порядок реализации

| Шаг | Что | Файлы | Зависимости |
|-----|-----|-------|-------------|
| 1 | Тесты на текущие пробелы (без секции) | test_funnel.py + test_funnel_results.py + test_apartments_service.py | Нет — зелёная база |
| 2 | SwitchTo рефакторинг | dialogs/funnel.py | Шаг 1 зелёный |
| 3 | Фильтр секции: state + getter + handler | dialogs/states.py, dialogs/funnel.py | Шаг 2 зелёный |
| 4 | Тесты на секцию | test_funnel.py + test_funnel_results.py | Шаг 3 |
| 5 | CRM integration тесты | test_funnel_crm_integration.py | Шаг 4 |
| 6 | E2E flow тесты | test_funnel_e2e_flow.py | Шаг 5 |

---

## 8. Acceptance Criteria

- [ ] `make test-unit` — все 350+ существующих тестов зелёные
- [ ] 52 новых теста зелёные
- [ ] Фильтр секции работает: select → save → filters → Qdrant MatchValue → results
- [ ] Back из pref_section → preferences (SwitchTo)
- [ ] Summary показывает выбранную секцию
- [ ] Zero suggestions включает rm_section
- [ ] `_build_apartment_filter({"section": "D-1"})` → `FieldCondition(key="section", match=MatchValue("D-1"))`
- [ ] `build_funnel_filters(section="D-1")` → `{"section": "D-1"}`
- [ ] `build_funnel_filters(section="any")` → section not in filters
- [ ] SwitchTo заменил 8 кастомных Button+handler
- [ ] `make check` (ruff + mypy) зелёный
