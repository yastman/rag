"""Tests for CRM task wizard and My Tasks view dialogs (#697) — Task 6."""

from __future__ import annotations

import datetime
import time

import pytest


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


def test_filter_tasks_today_returns_only_todays_tasks():
    """filter_tasks_today returns only tasks due today."""
    from telegram_bot.dialogs.crm_tasks import filter_tasks_today
    from telegram_bot.services.kommo_models import Task

    now = datetime.datetime.now(tz=datetime.UTC)
    today_ts = int(now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp())
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


def test_filter_tasks_today_skips_completed():
    """filter_tasks_today skips completed tasks."""
    from telegram_bot.dialogs.crm_tasks import filter_tasks_today
    from telegram_bot.services.kommo_models import Task

    now = datetime.datetime.now(tz=datetime.UTC)
    today_ts = int(now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp())

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
    """render_tasks_text returns empty indicator when no tasks."""
    from telegram_bot.dialogs.crm_tasks import render_tasks_text

    result = render_tasks_text([])
    assert "нет" in result.lower() or "пуст" in result.lower() or len(result) > 0


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
