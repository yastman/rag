"""CRM Lead dialogs: submenu, create wizard, my leads, search (#697).

Dialogs:
  leads_menu_dialog    — LeadsMenuSG.main  — navigation hub for leads
  create_lead_dialog   — CreateLeadSG.*    — multi-step wizard
  my_leads_dialog      — MyLeadsSG.main    — paginated list of manager's leads
  search_leads_dialog  — SearchLeadsSG.*   — search by query
"""

from __future__ import annotations

import logging
import operator
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput, TextInput
from aiogram_dialog.widgets.kbd import Back, Button, Cancel, Column, Select, Start
from aiogram_dialog.widgets.text import Format

from .crm_cards import format_lead_card
from .states import (
    CreateLeadSG,
    LeadsMenuSG,
    MyLeadsSG,
    SearchLeadsSG,
)


logger = logging.getLogger(__name__)

_PAGE_SIZE = 5


# ─────────────────────────────────────────────────────────────────────────────
# Leads Menu — getters & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_leads_menu_data(**kwargs: Any) -> dict[str, str]:
    """Getter: leads submenu navigation labels."""
    return {
        "title": "📋 Сделки",
        "btn_create": "➕ Создать сделку",
        "btn_my_leads": "🗂 Мои сделки",
        "btn_back": "← Назад",
    }


leads_menu_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Start(
                Format("{btn_create}"),
                id="leads_nav_create",
                state=CreateLeadSG.name,
            ),
            Start(
                Format("{btn_my_leads}"),
                id="leads_nav_my",
                state=MyLeadsSG.main,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_leads_menu_data,
        state=LeadsMenuSG.main,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Create Lead Wizard — getters, handlers & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_lead_name_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: lead name input prompt."""
    return {
        "prompt": "Введите название сделки:",
        "btn_cancel": "Отмена",
    }


async def get_lead_budget_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: lead budget input prompt."""
    return {
        "prompt": "Введите бюджет сделки (целое число в €, или 0 чтобы пропустить):",
        "btn_back": "← Назад",
    }


async def get_lead_pipeline_options(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter: pipeline list from Kommo (cached in dialog_data)."""
    pipelines: list[list[str]] = dialog_manager.dialog_data.get("_pipelines", [])
    if not pipelines:
        kommo = dialog_manager.middleware_data.get("kommo_client")
        if kommo is not None:
            try:
                pipeline_list = await kommo.list_pipelines()
                pipelines = [[p.name, str(p.id)] for p in pipeline_list]
            except Exception:
                logger.exception("Failed to fetch pipelines from Kommo")
                pipelines = []
        dialog_manager.dialog_data["_pipelines"] = pipelines

    items = [[name, pid] for name, pid in pipelines]
    return {
        "title": "Выберите pipeline (воронку):",
        "pipelines": items,
        "has_pipelines": bool(items),
        "btn_skip": "Пропустить",
        "btn_back": "← Назад",
    }


async def get_lead_summary_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter: lead preview for confirmation window."""
    data = dialog_manager.dialog_data
    name = data.get("name", "—")
    budget = data.get("budget")
    pipeline_name = data.get("pipeline_name", "не выбран")

    budget_str = f"{budget:,} €".replace(",", " ") if budget else "не указан"

    lines = [
        "📋 Предпросмотр сделки:\n",
        f"Название: {name}",
        f"Бюджет: {budget_str}",
        f"Pipeline: {pipeline_name}",
    ]
    return {
        "summary_text": "\n".join(lines),
        "btn_confirm": "✅ Создать",
        "btn_edit": "✏️ Изменить название",
        "btn_cancel": "Отмена",
    }


# Handlers


async def on_lead_name_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    text: str,
) -> None:
    """Save deal name and advance to budget step."""
    manager.dialog_data["name"] = text.strip()
    await manager.switch_to(CreateLeadSG.budget)


async def on_lead_budget_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    text: str,
) -> None:
    """Validate and save budget, then advance to pipeline step."""
    stripped = text.strip()
    try:
        value = int(stripped)
        if value < 0:
            raise ValueError("negative budget")
        manager.dialog_data["budget"] = value if value > 0 else None
        await manager.switch_to(CreateLeadSG.pipeline)
    except ValueError:
        await message.answer("Введите целое число ≥ 0 (например: 75000), или 0 чтобы пропустить.")


async def on_pipeline_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save selected pipeline and advance to summary."""
    pipelines: list[list[str]] = manager.dialog_data.get("_pipelines", [])
    pipeline_name = next(
        (name for name, pid in pipelines if pid == item_id),
        item_id,
    )
    manager.dialog_data["pipeline_id"] = int(item_id)
    manager.dialog_data["pipeline_name"] = pipeline_name
    await manager.switch_to(CreateLeadSG.summary)


async def on_pipeline_skip(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Skip pipeline selection and go to summary."""
    manager.dialog_data.pop("pipeline_id", None)
    manager.dialog_data["pipeline_name"] = "не выбран"
    await manager.switch_to(CreateLeadSG.summary)


async def on_lead_confirm(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Confirm: call kommo.create_lead() and close wizard."""
    kommo = manager.middleware_data.get("kommo_client")
    if kommo is None:
        if callback.message is not None:
            await callback.message.answer("❌ CRM-интеграция недоступна.")
        return

    from telegram_bot.services.kommo_models import LeadCreate

    data = manager.dialog_data
    payload = LeadCreate(
        name=data.get("name", "Новая сделка"),
        budget=data.get("budget"),
        pipeline_id=data.get("pipeline_id"),
    )

    try:
        lead = await kommo.create_lead(payload)
        from .crm_cards import format_lead_card

        text, keyboard = format_lead_card(lead)
        if callback.message is not None:
            await callback.message.answer(
                f"✅ Сделка создана!\n\n{text}",
                reply_markup=keyboard,
            )
    except Exception:
        logger.exception("Failed to create lead in Kommo")
        if callback.message is not None:
            await callback.message.answer("❌ Не удалось создать сделку. Попробуйте позже.")
        return

    await manager.done()


async def on_lead_edit(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Go back to name step for editing."""
    await manager.switch_to(CreateLeadSG.name)


create_lead_dialog = Dialog(
    # Step 1: Name
    Window(
        Format("{prompt}"),
        TextInput(id="lead_name", on_success=on_lead_name_entered),  # type: ignore[arg-type]
        Cancel(Format("{btn_cancel}")),
        getter=get_lead_name_prompt,
        state=CreateLeadSG.name,
    ),
    # Step 2: Budget
    Window(
        Format("{prompt}"),
        TextInput(id="lead_budget", on_success=on_lead_budget_entered),  # type: ignore[arg-type]
        Back(Format("{btn_back}")),
        getter=get_lead_budget_prompt,
        state=CreateLeadSG.budget,
    ),
    # Step 3: Pipeline
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pipeline",
                item_id_getter=operator.itemgetter(1),
                items="pipelines",
                on_click=on_pipeline_selected,
                when="has_pipelines",
            ),
        ),
        Button(Format("{btn_skip}"), id="pipeline_skip", on_click=on_pipeline_skip),
        Back(Format("{btn_back}")),
        getter=get_lead_pipeline_options,
        state=CreateLeadSG.pipeline,
    ),
    # Step 4: Summary + Confirm
    Window(
        Format("{summary_text}"),
        Button(Format("{btn_confirm}"), id="lead_confirm", on_click=on_lead_confirm),
        Button(Format("{btn_edit}"), id="lead_edit", on_click=on_lead_edit),
        Cancel(Format("{btn_cancel}")),
        getter=get_lead_summary_data,
        state=CreateLeadSG.summary,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# My Leads — getters, pagination handlers & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_my_leads_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter: fetch manager's leads with task counts and simple pagination (#731)."""
    kommo = dialog_manager.middleware_data.get("kommo_client")
    page = dialog_manager.dialog_data.get("page", 0)

    leads_text = "Нет сделок."
    total = 0

    if kommo is not None:
        try:
            config = dialog_manager.middleware_data.get("bot_config")
            manager_id: int | None = (
                getattr(config, "kommo_responsible_user_id", None) if config else None
            )
            leads = await kommo.search_leads(
                responsible_user_id=manager_id, limit=100, with_contacts=True
            )
            total = len(leads)

            # Batch-fetch open tasks for all manager's leads, group by entity_id (#731)
            task_counts: dict[int, int] = {}
            try:
                all_tasks = await kommo.get_tasks(
                    responsible_user_id=manager_id, is_completed=False
                )
                for t in all_tasks:
                    if t.entity_id:
                        task_counts[t.entity_id] = task_counts.get(t.entity_id, 0) + 1
            except Exception:
                logger.exception("Failed to fetch tasks for lead cards")

            start = page * _PAGE_SIZE
            page_leads = leads[start : start + _PAGE_SIZE]
            if page_leads:
                cards = []
                for lead in page_leads:
                    text, _ = format_lead_card(lead, task_count=task_counts.get(lead.id, 0))
                    cards.append(text)
                leads_text = "\n\n".join(cards)
            else:
                leads_text = "Нет сделок на этой странице."
        except Exception:
            logger.exception("Failed to fetch my leads from Kommo")
            leads_text = "Ошибка загрузки сделок."

    has_prev = page > 0
    has_next = (page + 1) * _PAGE_SIZE < total

    return {
        "title": f"🗂 Мои сделки (стр. {page + 1})",
        "leads_text": leads_text,
        "has_prev": has_prev,
        "has_next": has_next,
        "btn_prev": "◀ Предыдущие",
        "btn_next": "Следующие ▶",
        "btn_back": "← Назад",
    }


async def on_my_leads_prev(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Go to previous page of leads."""
    page = manager.dialog_data.get("page", 0)
    if page > 0:
        manager.dialog_data["page"] = page - 1


async def on_my_leads_next(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Go to next page of leads."""
    page = manager.dialog_data.get("page", 0)
    manager.dialog_data["page"] = page + 1


my_leads_dialog = Dialog(
    Window(
        Format("{title}\n\n{leads_text}"),
        Button(
            Format("{btn_prev}"),
            id="my_leads_prev",
            on_click=on_my_leads_prev,
            when="has_prev",
        ),
        Button(
            Format("{btn_next}"),
            id="my_leads_next",
            on_click=on_my_leads_next,
            when="has_next",
        ),
        Cancel(Format("{btn_back}")),
        getter=get_my_leads_data,
        state=MyLeadsSG.main,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Search Leads — getters, handlers & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_search_leads_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: lead search prompt."""
    return {
        "prompt": "Введите текст для поиска сделок:",
        "btn_cancel": "Отмена",
    }


async def get_search_leads_results(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter: execute lead search and format results."""
    kommo = dialog_manager.middleware_data.get("kommo_client")
    query = dialog_manager.dialog_data.get("search_query", "")

    results_text = "Ничего не найдено."

    if kommo is not None and query:
        try:
            leads = await kommo.search_leads(query=query, limit=20)
            if leads:
                cards = []
                for lead in leads:
                    text, _ = format_lead_card(lead)
                    cards.append(text)
                results_text = "\n\n".join(cards)
        except Exception:
            logger.exception("Failed to search leads in Kommo")
            results_text = "Ошибка поиска. Попробуйте позже."
    elif not kommo:
        results_text = "CRM-интеграция недоступна."

    return {
        "title": f'🔍 Результаты поиска: "{query}"',
        "results_text": results_text,
        "btn_back": "← Назад",
        "btn_cancel": "Закрыть",
    }


async def on_search_leads_query(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    """Save search query and switch to results."""
    manager.dialog_data["search_query"] = message.text or ""
    await manager.switch_to(SearchLeadsSG.results)


search_leads_dialog = Dialog(
    # Step 1: Query input
    Window(
        Format("{prompt}"),
        MessageInput(func=on_search_leads_query),
        Cancel(Format("{btn_cancel}")),
        getter=get_search_leads_prompt,
        state=SearchLeadsSG.query,
    ),
    # Step 2: Results
    Window(
        Format("{title}\n\n{results_text}"),
        Back(Format("{btn_back}")),
        Cancel(Format("{btn_cancel}")),
        getter=get_search_leads_results,
        state=SearchLeadsSG.results,
    ),
)
