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


class FunnelSG(StatesGroup):
    """Property search funnel (***REMOVED***628, refactored ***REMOVED***697)."""

    complex = State()  ***REMOVED*** Step 1: комплекс
    property_type = State()  ***REMOVED*** Step 2: тип квартиры
    budget = State()  ***REMOVED*** Step 3: бюджет
    preferences = State()  ***REMOVED*** Step 4: доп. пожелания (multi-select menu)
    pref_floor = State()  ***REMOVED*** Step 4a: этаж sub-options
    pref_view = State()  ***REMOVED*** Step 4b: вид sub-options
    pref_furnished = State()  ***REMOVED*** Step 4c: мебель sub-options
    pref_promotion = State()  ***REMOVED*** Step 4d: акции sub-options
    summary = State()  ***REMOVED*** Step 5: саммари + confirmation
    change_filter = State()  ***REMOVED*** Step 5a: выбор фильтра для изменения
    results = State()  ***REMOVED*** Step 6: результаты


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
    due_date = State()  ***REMOVED*** Step 2: срок выполнения
    lead_id = State()  ***REMOVED*** Step 3: ID сделки
    summary = State()  ***REMOVED*** Step 4: подтверждение


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


class AIAdvisorSG(StatesGroup):
    """AI advisor dialog (***REMOVED***697)."""

    main = State()
