"""Filter dialog assembly — combines all windows into the Dialog object."""

from __future__ import annotations

from aiogram_dialog import Dialog

from telegram_bot.dialogs.filter.handlers import on_filter_dialog_start
from telegram_bot.dialogs.filter.windows import (
    area_window,
    budget_window,
    city_window,
    complex_window,
    floor_window,
    furnished_window,
    hub_window,
    promotion_window,
    rooms_window,
    view_window,
)


filter_dialog = Dialog(
    hub_window,
    city_window,
    rooms_window,
    budget_window,
    view_window,
    area_window,
    floor_window,
    complex_window,
    furnished_window,
    promotion_window,
    on_start=on_filter_dialog_start,
)
