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
    """Property search funnel (#628, refactored #697)."""

    complex = State()  # Step 1: комплекс
    property_type = State()  # Step 2: тип квартиры
    budget = State()  # Step 3: бюджет
    preferences = State()  # Step 4: доп. пожелания (multi-select menu)
    pref_floor = State()  # Step 4a: этаж sub-options
    pref_view = State()  # Step 4b: вид sub-options
    pref_furnished = State()  # Step 4c: мебель sub-options
    pref_promotion = State()  # Step 4d: акции sub-options
    summary = State()  # Step 5: саммари + confirmation
    change_filter = State()  # Step 5a: выбор фильтра для изменения
    results = State()  # Step 6: результаты


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()


class CrmSubmenuSG(StatesGroup):
    """CRM submenu (manager only) — kept for backward compatibility."""

    main = State()


class CRMMenuSG(StatesGroup):
    """CRM navigation hub (#697) — refactored from CrmSubmenuSG."""

    main = State()


class CreateLeadSG(StatesGroup):
    """Create lead wizard (#697)."""

    name = State()  # Step 1: название сделки
    budget = State()  # Step 2: бюджет
    pipeline = State()  # Step 3: выбор pipeline
    summary = State()  # Step 4: подтверждение


class CreateContactSG(StatesGroup):
    """Create contact wizard (#697)."""

    first_name = State()  # Step 1: имя
    last_name = State()  # Step 2: фамилия
    phone = State()  # Step 3: телефон
    email = State()  # Step 4: email
    summary = State()  # Step 5: подтверждение


class CreateTaskSG(StatesGroup):
    """Create task wizard (#697)."""

    text = State()  # Step 1: текст задачи
    due_date = State()  # Step 2: срок выполнения
    lead_id = State()  # Step 3: ID сделки
    summary = State()  # Step 4: подтверждение


class CreateNoteSG(StatesGroup):
    """Create note wizard (#697)."""

    entity_type = State()  # Step 1: тип сущности (leads/contacts)
    entity_id = State()  # Step 2: ID сущности
    text = State()  # Step 3: текст заметки
    summary = State()  # Step 4: подтверждение


class SearchSG(StatesGroup):
    """CRM search dialog (#697)."""

    query = State()  # Step 1: поисковый запрос
    results = State()  # Step 2: результаты


class AIAdvisorSG(StatesGroup):
    """AI advisor dialog (#697)."""

    main = State()
