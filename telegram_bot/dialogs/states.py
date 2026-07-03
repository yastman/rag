"""FSM states for all dialogs (aiogram-dialog)."""

from aiogram.fsm.state import State, StatesGroup


class ClientMenuSG(StatesGroup):
    """Client main menu."""

    main = State()


class SettingsSG(StatesGroup):
    """User settings dialog."""

    main = State()
    language = State()


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


class ViewingSG(StatesGroup):
    """Viewing appointment wizard."""

    date = State()  # Шаг 1: желаемая дата → phone_collector FSM


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()


class HandoffSG(StatesGroup):
    """Manager handoff qualification (#730)."""

    goal = State()
    contact = State()


class FilterSG(StatesGroup):
    """Filter panel dialog (aiogram-dialog, replaces custom inline filter panel)."""

    hub = State()  # Main filter hub: summary + 9 filter buttons
    city = State()  # City sub-menu
    rooms = State()  # Rooms sub-menu
    budget = State()  # Budget sub-menu
    view = State()  # View sub-menu
    area = State()  # Area sub-menu
    floor = State()  # Floor sub-menu
    complex_name = State()  # Complex sub-menu
    furnished = State()  # Furnished sub-menu
    promotion = State()  # Promotion sub-menu


class CatalogSG(StatesGroup):
    """Dialog-owned catalog flow."""

    results = State()
    empty = State()
    details = State()


class DemoSG(StatesGroup):
    """Demo apartment search dialog (aiogram-dialog, #907)."""

    intro = State()  # Step 1: query input (text or voice)
    results = State()  # Step 2: search results display


# ---------------------------------------------------------------------------
# Compatibility stubs — states removed with the archived CRM voice/AI path.
# The dialog modules that reference these remain in-tree but are not on the
# active production path.  Stubs prevent ImportError during collection.
# ---------------------------------------------------------------------------


class AIAdvisorSG(StatesGroup):
    """AI Advisor dialog states (archived — not on active production path)."""

    main = State()
    loading = State()
    result = State()


class CrmQuickActionSG(StatesGroup):
    """CRM quick-action dialog states (archived — not on active production path)."""

    waiting_note = State()
    waiting_task = State()
    edit_task_choose_field = State()
    edit_task_text = State()
    edit_task_date = State()


class ContactsMenuSG(StatesGroup):
    """Contacts navigation hub (archived CRM path)."""

    main = State()


class CreateContactSG(StatesGroup):
    """Create contact wizard (archived CRM path)."""

    name = State()
    phone = State()
    email = State()
    confirm = State()


class SearchContactsSG(StatesGroup):
    """Search contacts dialog (archived CRM path)."""

    query = State()
    results = State()


class LeadsMenuSG(StatesGroup):
    """Leads navigation hub (archived CRM path)."""

    main = State()


class CRMMenuSG(StatesGroup):
    """CRM top-level navigation menu (archived CRM path)."""

    main = State()


class ManagerMenuSG(StatesGroup):
    """Manager menu dialog (archived CRM path)."""

    main = State()


class CreateLeadSG(StatesGroup):
    """Create lead wizard (archived CRM path)."""

    name = State()
    phone = State()
    budget = State()
    confirm = State()


class SearchSG(StatesGroup):
    """Generic search dialog (archived CRM path)."""

    query = State()
    results = State()


class CreateNoteSG(StatesGroup):
    """Create note dialog (archived CRM path)."""

    text = State()
    confirm = State()


class CreateTaskSG(StatesGroup):
    """Create task wizard (archived CRM path)."""

    title = State()
    due_date = State()
    confirm = State()


class MyTasksSG(StatesGroup):
    """My tasks view dialog (archived CRM path)."""

    main = State()
    task_detail = State()


class TasksMenuSG(StatesGroup):
    """Tasks navigation menu (archived CRM path)."""

    main = State()
