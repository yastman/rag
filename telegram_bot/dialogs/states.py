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
    """Property search funnel (***REMOVED***628)."""

    location = State()  ***REMOVED*** Step 1: район
    property_type = State()  ***REMOVED*** Step 2: тип квартиры
    budget = State()  ***REMOVED*** Step 3: бюджет
    refine_or_show = State()  ***REMOVED*** Step 4: показать / уточнить
    floor = State()  ***REMOVED*** Step 4a: этаж (optional)
    view = State()  ***REMOVED*** Step 4b: вид (optional)
    results = State()  ***REMOVED*** Step 5: результаты


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()


class CrmSubmenuSG(StatesGroup):
    """CRM submenu (manager only)."""

    main = State()
