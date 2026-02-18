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
    """BANT sales funnel."""

    property_type = State()
    area = State()
    budget = State()
    timeline = State()
    results = State()


class FaqSG(StatesGroup):
    """FAQ submenu."""

    main = State()
