"""FSM states for all dialogs (aiogram-dialog)."""

from aiogram.fsm.state import State, StatesGroup


class ClientMenuSG(StatesGroup):
    """Client main menu."""

    main = State()


class ManagerMenuSG(StatesGroup):
    """Manager main menu."""

    main = State()


class SettingsSG(StatesGroup):
    """User settings dialog."""

    main = State()
    language = State()
    crm = State()  ***REMOVED*** CRM settings section (***REMOVED***697 Task 10)


class FunnelSG(StatesGroup):
    """Property search funnel (***REMOVED***628, refactored ***REMOVED***697)."""

    city = State()  ***REMOVED*** Step 1: город/курорт
    property_type = State()  ***REMOVED*** Step 2: тип квартиры
    budget = State()  ***REMOVED*** Step 3: бюджет
    preferences = State()  ***REMOVED*** Step 4: доп. пожелания (multi-select menu)
    pref_floor = State()  ***REMOVED*** Step 4a: этаж sub-options
    pref_view = State()  ***REMOVED*** Step 4b: вид sub-options
    pref_furnished = State()  ***REMOVED*** Step 4c: мебель sub-options
    pref_promotion = State()  ***REMOVED*** Step 4d: акции sub-options
    pref_area = State()  ***REMOVED*** Step 4f: площадь sub-options
    pref_complex = State()  ***REMOVED*** Step 4e: комплекс sub-options
    pref_section = State()  ***REMOVED*** Step 4g: секция sub-options
    summary = State()  ***REMOVED*** Step 5: саммари + confirmation
    change_filter = State()  ***REMOVED*** Step 5a: выбор фильтра для изменения


class ViewingSG(StatesGroup):
    """Viewing appointment wizard."""

    date = State()  ***REMOVED*** Шаг 1: желаемая дата → phone_collector FSM


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()


class CrmSubmenuSG(StatesGroup):
    """CRM submenu (manager only) — kept for backward compatibility."""

    main = State()


class CRMMenuSG(StatesGroup):
    """CRM navigation hub (***REMOVED***697) — refactored from CrmSubmenuSG."""

    main = State()


class CreateLeadSG(StatesGroup):
    """Create lead wizard (***REMOVED***697)."""

    name = State()  ***REMOVED*** Step 1: название сделки
    budget = State()  ***REMOVED*** Step 2: бюджет
    pipeline = State()  ***REMOVED*** Step 3: выбор pipeline
    summary = State()  ***REMOVED*** Step 4: подтверждение


class CreateContactSG(StatesGroup):
    """Create contact wizard (***REMOVED***697)."""

    first_name = State()  ***REMOVED*** Step 1: имя
    last_name = State()  ***REMOVED*** Step 2: фамилия
    phone = State()  ***REMOVED*** Step 3: телефон
    email = State()  ***REMOVED*** Step 4: email
    summary = State()  ***REMOVED*** Step 5: подтверждение


class CreateTaskSG(StatesGroup):
    """Create task wizard (***REMOVED***697)."""

    text = State()  ***REMOVED*** Step 1: текст задачи
    task_type = State()  ***REMOVED*** Step 2: тип задачи (звонок/встреча/другое)
    lead_id = State()  ***REMOVED*** Step 3: привязка к сделке
    due_date = State()  ***REMOVED*** Step 4: срок выполнения
    summary = State()  ***REMOVED*** Step 5: подтверждение


class TasksMenuSG(StatesGroup):
    """Tasks navigation submenu."""

    main = State()


class MyTasksSG(StatesGroup):
    """My Tasks view (***REMOVED***697)."""

    filter = State()  ***REMOVED*** Step 1: выбор фильтра (все/сегодня/просроченные)
    list = State()  ***REMOVED*** Step 2: список задач с пагинацией


class CreateNoteSG(StatesGroup):
    """Create note wizard (***REMOVED***697)."""

    entity_type = State()  ***REMOVED*** Step 1: тип сущности (leads/contacts)
    entity_id = State()  ***REMOVED*** Step 2: ID сущности
    text = State()  ***REMOVED*** Step 3: текст заметки
    summary = State()  ***REMOVED*** Step 4: подтверждение


class SearchSG(StatesGroup):
    """CRM search dialog (***REMOVED***697)."""

    query = State()  ***REMOVED*** Step 1: поисковый запрос
    results = State()  ***REMOVED*** Step 2: результаты


class LeadsMenuSG(StatesGroup):
    """Leads navigation submenu (***REMOVED***697)."""

    main = State()


class MyLeadsSG(StatesGroup):
    """My leads list view (***REMOVED***697)."""

    main = State()


class SearchLeadsSG(StatesGroup):
    """Lead search dialog (***REMOVED***697)."""

    query = State()
    results = State()


class ContactsMenuSG(StatesGroup):
    """Contacts navigation submenu (***REMOVED***697)."""

    main = State()


class SearchContactsSG(StatesGroup):
    """Contact search dialog (***REMOVED***697)."""

    query = State()
    results = State()


class AIAdvisorSG(StatesGroup):
    """AI advisor dialog (***REMOVED***697)."""

    main = State()
    loading = State()  ***REMOVED*** "⏳ Анализирую данные..."
    result = State()  ***REMOVED*** LLM response display


class CrmQuickActionSG(StatesGroup):
    """Quick CRM actions triggered from card inline buttons (***REMOVED***697 Task 8)."""

    waiting_note = State()  ***REMOVED*** waiting for note text (lead or contact)
    waiting_task = State()  ***REMOVED*** waiting for task text (lead)
    edit_task_choose_field = State()  ***REMOVED*** choose what to edit (text or due date)
    edit_task_text = State()  ***REMOVED*** waiting for new task text
    edit_task_date = State()  ***REMOVED*** waiting for new due date


class HandoffSG(StatesGroup):
    """Manager handoff qualification (***REMOVED***730)."""

    goal = State()
    contact = State()


class FilterSG(StatesGroup):
    """Filter panel dialog (aiogram-dialog, replaces custom inline filter panel)."""

    hub = State()  ***REMOVED*** Main filter hub: summary + 9 filter buttons
    city = State()  ***REMOVED*** City sub-menu
    rooms = State()  ***REMOVED*** Rooms sub-menu
    budget = State()  ***REMOVED*** Budget sub-menu
    view = State()  ***REMOVED*** View sub-menu
    area = State()  ***REMOVED*** Area sub-menu
    floor = State()  ***REMOVED*** Floor sub-menu
    complex_name = State()  ***REMOVED*** Complex sub-menu
    furnished = State()  ***REMOVED*** Furnished sub-menu
    promotion = State()  ***REMOVED*** Promotion sub-menu


class CatalogSG(StatesGroup):
    """Dialog-owned catalog flow."""

    results = State()
    empty = State()
    details = State()


class DemoSG(StatesGroup):
    """Demo apartment search dialog (aiogram-dialog, ***REMOVED***907)."""

    intro = State()  ***REMOVED*** Step 1: query input (text or voice)
    results = State()  ***REMOVED*** Step 2: search results display
