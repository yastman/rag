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
    """Property search funnel (#628)."""

    location = State()  # Step 1: район
    property_type = State()  # Step 2: тип квартиры
    budget = State()  # Step 3: бюджет
    refine_or_show = State()  # Step 4: показать / уточнить
    floor = State()  # Step 4a: этаж (optional)
    view = State()  # Step 4b: вид (optional)
    results = State()  # Step 5: результаты


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()


class CrmSubmenuSG(StatesGroup):
    """CRM submenu (manager only)."""

    main = State()
