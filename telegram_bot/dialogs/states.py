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
    crm = State()  # CRM settings section (#697 Task 10)


class FunnelSG(StatesGroup):
    """Property search funnel (#628, refactored #697)."""

    city = State()  # Step 1: город/курорт
    property_type = State()  # Step 2: тип квартиры
    budget = State()  # Step 3: бюджет
    preferences = State()  # Step 4: доп. пожелания (multi-select menu)
    pref_floor = State()  # Step 4a: этаж sub-options
    pref_view = State()  # Step 4b: вид sub-options
    pref_furnished = State()  # Step 4c: мебель sub-options
    pref_promotion = State()  # Step 4d: акции sub-options
    pref_area = State()  # Step 4f: площадь sub-options
    pref_complex = State()  # Step 4e: комплекс sub-options
    pref_section = State()  # Step 4g: секция sub-options
    summary = State()  # Step 5: саммари + confirmation
    change_filter = State()  # Step 5a: выбор фильтра для изменения
    results = State()  # Step 6: список результатов (list view)


class ViewingSG(StatesGroup):
    """Viewing appointment wizard."""

    objects = State()  # Шаг 1: выбор объектов из закладок
    objects_text = State()  # Шаг 1b: ручной ввод (опционально)
    date = State()  # Шаг 2: желаемая дата
    phone = State()  # Шаг 3: номер телефона
    summary = State()  # Шаг 4: подтверждение + CRM


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
    task_type = State()  # Step 2: тип задачи (звонок/встреча/другое)
    lead_id = State()  # Step 3: привязка к сделке
    due_date = State()  # Step 4: срок выполнения
    summary = State()  # Step 5: подтверждение


class TasksMenuSG(StatesGroup):
    """Tasks navigation submenu."""

    main = State()


class MyTasksSG(StatesGroup):
    """My Tasks view (#697)."""

    filter = State()  # Step 1: выбор фильтра (все/сегодня/просроченные)
    list = State()  # Step 2: список задач с пагинацией


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


class LeadsMenuSG(StatesGroup):
    """Leads navigation submenu (#697)."""

    main = State()


class MyLeadsSG(StatesGroup):
    """My leads list view (#697)."""

    main = State()


class SearchLeadsSG(StatesGroup):
    """Lead search dialog (#697)."""

    query = State()
    results = State()


class ContactsMenuSG(StatesGroup):
    """Contacts navigation submenu (#697)."""

    main = State()


class SearchContactsSG(StatesGroup):
    """Contact search dialog (#697)."""

    query = State()
    results = State()


class AIAdvisorSG(StatesGroup):
    """AI advisor dialog (#697)."""

    main = State()
    loading = State()  # "⏳ Анализирую данные..."
    result = State()  # LLM response display


class CrmQuickActionSG(StatesGroup):
    """Quick CRM actions triggered from card inline buttons (#697 Task 8)."""

    waiting_note = State()  # waiting for note text (lead or contact)
    waiting_task = State()  # waiting for task text (lead)
    edit_task_choose_field = State()  # choose what to edit (text or due date)
    edit_task_text = State()  # waiting for new task text
    edit_task_date = State()  # waiting for new due date


class HandoffSG(StatesGroup):
    """Manager handoff qualification (#730)."""

    goal = State()
    contact = State()


class DemoSG(StatesGroup):
    """Demo apartment search dialog (aiogram-dialog, #907)."""

    intro = State()  # Step 1: query input (text or voice)
    results = State()  # Step 2: search results display
