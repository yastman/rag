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
    """CRM submenu (manager only)."""

    main = State()
