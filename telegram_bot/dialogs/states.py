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
    """CRM submenu (manager only)."""

    main = State()
