"""Tests for CRM task wizard and My Tasks view dialogs (#697) — Task 6."""

from __future__ import annotations

import datetime
import time
import types

import pytest


def _freeze_crm_tasks_now(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime.datetime) -> None:
    """Freeze ``datetime.datetime.now`` inside ``telegram_bot.dialogs.crm_tasks``.

    ``filter_tasks_today`` calls ``datetime.datetime.now(tz=UTC)`` to compute
    today's window. If the test runs across midnight UTC, the test's
    ``today_ts`` (computed from a separate ``datetime.now()``) lands on a
    different date than the production's ``today_start``/``today_end``,
    causing a flake (#1515 S4). This helper replaces the ``datetime`` module
    binding inside ``crm_tasks`` with a fake namespace whose ``datetime``
    class returns ``fixed_now`` from ``now()``, so both the test setup and
    production code see the same instant. ``freezegun`` is intentionally not
    introduced as a new dep.
    """
    from telegram_bot.dialogs import crm_tasks as crm_tasks_mod

    class _FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    fake_dt_module = types.SimpleNamespace(
        datetime=_FrozenDatetime,
        UTC=datetime.UTC,
        timezone=datetime.timezone,
        timedelta=datetime.timedelta,
    )
    monkeypatch.setattr(crm_tasks_mod, "datetime", fake_dt_module)


# --- MyTasksSG states ---


def test_my_tasks_sg_has_filter_state():
    """MyTasksSG has 'filter' state for filter selection."""
    from telegram_bot.dialogs.states import MyTasksSG

    assert hasattr(MyTasksSG, "filter")


def test_my_tasks_sg_has_list_state():
    """MyTasksSG has 'list' state for task list view."""
    from telegram_bot.dialogs.states import MyTasksSG

    assert hasattr(MyTasksSG, "list")


def test_create_task_sg_has_task_type_state():
    """CreateTaskSG has 'task_type' state for task type selection."""
    from telegram_bot.dialogs.states import CreateTaskSG

    assert hasattr(CreateTaskSG, "task_type")


# --- parse_due_date helper ---


def test_parse_due_date_valid():
    """parse_due_date converts DD.MM.YYYY string to Unix timestamp."""
    from telegram_bot.dialogs.crm_tasks import parse_due_date

    ts = parse_due_date("31.12.2026")
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
    assert dt.day == 31
    assert dt.month == 12
    assert dt.year == 2026


def test_parse_due_date_returns_int():
    """parse_due_date returns an integer Unix timestamp."""
    from telegram_bot.dialogs.crm_tasks import parse_due_date

    ts = parse_due_date("01.01.2027")
    assert isinstance(ts, int)


def test_parse_due_date_invalid_raises():
    """parse_due_date raises ValueError for invalid date strings."""
    from telegram_bot.dialogs.crm_tasks import parse_due_date

    with pytest.raises(ValueError):
        parse_due_date("not-a-date")

    with pytest.raises(ValueError):
        parse_due_date("32.13.2026")

    with pytest.raises(ValueError):
        parse_due_date("2026-12-31")  # wrong format


def test_parse_due_date_past_raises():
    """parse_due_date raises ValueError for past dates."""
    from telegram_bot.dialogs.crm_tasks import parse_due_date

    with pytest.raises(ValueError):
        parse_due_date("01.01.2000")


# --- filter_tasks helpers ---


def test_filter_tasks_today_returns_only_todays_tasks(monkeypatch):
    """filter_tasks_today returns only tasks due today."""
    from telegram_bot.dialogs.crm_tasks import filter_tasks_today
    from telegram_bot.services.kommo_models import Task

    # Freeze production's "now" to a deterministic UTC noon so the test's
    # today_ts/tomorrow_ts/yesterday_ts and the production's today_start/end
    # observe the same date even if the test runs across midnight UTC.
    fixed_now = datetime.datetime(2026, 6, 15, 12, 0, 0, tzinfo=datetime.UTC)
    _freeze_crm_tasks_now(monkeypatch, fixed_now)

    today_ts = int(fixed_now.timestamp())
    tomorrow_ts = today_ts + 86400
    yesterday_ts = today_ts - 86400

    tasks = [
        Task(id=1, text="Today", complete_till=today_ts, is_completed=False),
        Task(id=2, text="Tomorrow", complete_till=tomorrow_ts, is_completed=False),
        Task(id=3, text="Yesterday", complete_till=yesterday_ts, is_completed=False),
    ]

    result = filter_tasks_today(tasks)
    assert len(result) == 1
    assert result[0].id == 1


def test_filter_tasks_overdue_returns_only_overdue():
    """filter_tasks_overdue returns tasks past due and not completed."""
    from telegram_bot.dialogs.crm_tasks import filter_tasks_overdue
    from telegram_bot.services.kommo_models import Task

    now = int(time.time())
    past_ts = now - 86400  # yesterday
    future_ts = now + 86400  # tomorrow

    tasks = [
        Task(id=1, text="Overdue", complete_till=past_ts, is_completed=False),
        Task(id=2, text="Future", complete_till=future_ts, is_completed=False),
        Task(id=3, text="Done", complete_till=past_ts, is_completed=True),
    ]

    result = filter_tasks_overdue(tasks)
    assert len(result) == 1
    assert result[0].id == 1


def test_filter_tasks_today_skips_completed(monkeypatch):
    """filter_tasks_today skips completed tasks."""
    from telegram_bot.dialogs.crm_tasks import filter_tasks_today
    from telegram_bot.services.kommo_models import Task

    fixed_now = datetime.datetime(2026, 6, 15, 12, 0, 0, tzinfo=datetime.UTC)
    _freeze_crm_tasks_now(monkeypatch, fixed_now)

    today_ts = int(fixed_now.timestamp())

    tasks = [
        Task(id=1, text="Done today", complete_till=today_ts, is_completed=True),
    ]

    result = filter_tasks_today(tasks)
    assert result == []


# --- Dialog object export ---


def test_create_task_dialog_exported():
    """crm_tasks module exports create_task_dialog."""
    from telegram_bot.dialogs import crm_tasks

    assert hasattr(crm_tasks, "create_task_dialog")


def test_my_tasks_dialog_exported():
    """crm_tasks module exports my_tasks_dialog."""
    from telegram_bot.dialogs import crm_tasks

    assert hasattr(crm_tasks, "my_tasks_dialog")


def test_create_task_dialog_is_dialog():
    """create_task_dialog is an aiogram-dialog Dialog instance."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_tasks import create_task_dialog

    assert isinstance(create_task_dialog, Dialog)


def test_my_tasks_dialog_is_dialog():
    """my_tasks_dialog is an aiogram-dialog Dialog instance."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_tasks import my_tasks_dialog

    assert isinstance(my_tasks_dialog, Dialog)


# --- task_type_id mapping ---


def test_task_type_id_from_key_call():
    """task_type_id_from_key maps 'call' to Kommo task type ID 1."""
    from telegram_bot.dialogs.crm_tasks import task_type_id_from_key

    assert task_type_id_from_key("call") == 1


def test_task_type_id_from_key_meeting():
    """task_type_id_from_key maps 'meeting' to Kommo task type ID 2."""
    from telegram_bot.dialogs.crm_tasks import task_type_id_from_key

    assert task_type_id_from_key("meeting") == 2


def test_task_type_id_from_key_other():
    """task_type_id_from_key maps 'other' to Kommo task type ID 3."""
    from telegram_bot.dialogs.crm_tasks import task_type_id_from_key

    assert task_type_id_from_key("other") == 3


def test_task_type_id_from_key_unknown_raises():
    """task_type_id_from_key raises KeyError for unknown keys."""
    from telegram_bot.dialogs.crm_tasks import task_type_id_from_key

    with pytest.raises(KeyError):
        task_type_id_from_key("invalid")


# --- render_tasks_text helper ---


def test_render_tasks_text_empty():
    """render_tasks_text returns the canonical empty-state message when no tasks."""
    from telegram_bot.dialogs.crm_tasks import render_tasks_text

    result = render_tasks_text([])
    # Must be exactly the canonical empty-state string. The previous loose
    # assertion (`len(result) > 0`) accepted any non-empty wrong output.
    assert result == "Задач нет."


def test_render_tasks_text_single_task():
    """render_tasks_text includes task text and ID."""
    from telegram_bot.dialogs.crm_tasks import render_tasks_text
    from telegram_bot.services.kommo_models import Task

    task = Task(id=42, text="Call client back", is_completed=False)
    result = render_tasks_text([task])

    assert "42" in result
    assert "Call client back" in result


def test_render_tasks_text_multiple_tasks():
    """render_tasks_text includes all tasks."""
    from telegram_bot.dialogs.crm_tasks import render_tasks_text
    from telegram_bot.services.kommo_models import Task

    tasks = [
        Task(id=1, text="First task", is_completed=False),
        Task(id=2, text="Second task", is_completed=False),
    ]
    result = render_tasks_text(tasks)

    assert "First task" in result
    assert "Second task" in result


# --- get_task_list: edit_tasks data ---


async def test_get_task_list_includes_edit_tasks():
    """get_task_list getter returns edit_tasks for active tasks on page."""
    from unittest.mock import AsyncMock, MagicMock

    from telegram_bot.dialogs.crm_tasks import get_task_list
    from telegram_bot.services.kommo_models import Task

    kommo = AsyncMock()
    kommo.get_tasks = AsyncMock(
        return_value=[
            Task(id=10, text="Edit me", is_completed=False),
            Task(id=11, text="Also active", is_completed=False),
        ]
    )

    manager = MagicMock()
    manager.middleware_data = {"kommo_client": kommo}
    manager.dialog_data = {"task_filter": "all", "page": 0}

    result = await get_task_list(dialog_manager=manager)

    assert "edit_tasks" in result
    ids = [item_id for _, item_id in result["edit_tasks"]]
    assert "10" in ids
    assert "11" in ids


async def test_get_task_list_edit_tasks_excludes_completed():
    """get_task_list edit_tasks does not include completed tasks."""
    from unittest.mock import AsyncMock, MagicMock

    from telegram_bot.dialogs.crm_tasks import get_task_list
    from telegram_bot.services.kommo_models import Task

    kommo = AsyncMock()
    kommo.get_tasks = AsyncMock(
        return_value=[
            Task(id=10, text="Active", is_completed=False),
            Task(id=20, text="Done", is_completed=True),
        ]
    )

    manager = MagicMock()
    manager.middleware_data = {"kommo_client": kommo}
    manager.dialog_data = {"task_filter": "all", "page": 0}

    result = await get_task_list(dialog_manager=manager)

    ids = [item_id for _, item_id in result["edit_tasks"]]
    assert "10" in ids
    assert "20" not in ids


# --- on_task_edit_from_list ---


async def test_on_task_edit_from_list_starts_quick_actions_dialog():
    """on_task_edit_from_list opens CrmQuickActionsDialog with task id (#2053)."""
    from unittest.mock import AsyncMock, MagicMock

    from aiogram_dialog import ShowMode, StartMode

    from telegram_bot.dialogs.crm_tasks import on_task_edit_from_list
    from telegram_bot.dialogs.states import CrmQuickActionSG

    callback = AsyncMock()
    callback.message = AsyncMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.start = AsyncMock()

    await on_task_edit_from_list(callback, widget, manager, item_id="42")

    manager.start.assert_awaited_once()
    args = manager.start.call_args
    assert args.args[0] is CrmQuickActionSG.edit_task_choose_field
    assert args.kwargs["data"] == {"edit_task_id": 42}
    assert args.kwargs["mode"] is StartMode.RESET_STACK
    assert args.kwargs["show_mode"] is ShowMode.SEND
    callback.answer.assert_awaited()
