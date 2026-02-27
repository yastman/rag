"""CRM Note wizard dialog (aiogram-dialog) — #697.

Task 7: CreateNoteWizard
- text → entity_type → entity_id (if entity_type != none) → summary → confirm
"""

from __future__ import annotations

import logging
import operator
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import ManagedTextInput, TextInput
from aiogram_dialog.widgets.kbd import Back, Button, Cancel, Column, Select
from aiogram_dialog.widgets.text import Const, Format

from .states import CreateNoteSG


logger = logging.getLogger(__name__)

# --- Constants ---

# Entity type options: (label, key) — 'none' skips entity selection
NOTE_ENTITY_TYPES: list[tuple[str, str]] = [
    ("📋 К сделке", "leads"),
    ("👤 К контакту", "contacts"),
    ("— Без привязки", "none"),
]


# --- Helpers ---


def build_note_summary(
    *,
    text: str,
    entity_type: str | None,
    entity_id: int | None,
) -> str:
    """Format note preview text for the summary window.

    Args:
        text: Note text content.
        entity_type: 'leads', 'contacts', or None.
        entity_id: ID of the attached entity, or None.

    Returns:
        Formatted preview string for Telegram message.
    """
    entity_label = ""
    if entity_type == "leads" and entity_id is not None:
        entity_label = f"📋 Сделка #{entity_id}"
    elif entity_type == "contacts" and entity_id is not None:
        entity_label = f"👤 Контакт #{entity_id}"
    else:
        entity_label = "— без привязки"

    lines = [
        "📝 *Подтверждение заметки*",
        "",
        f"Текст: {text}",
        f"Привязка: {entity_label}",
        "",
        "Сохранить заметку?",
    ]
    return "\n".join(lines)


# --- Getters ---


async def get_note_text_data(**kwargs: Any) -> dict[str, str]:
    """Getter for note text input window."""
    return {"title": "📝 Создание заметки\n\nШаг 1/4: Введите текст заметки:"}


async def get_entity_type_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for entity type selection window."""
    return {
        "title": "📝 Создание заметки\n\nШаг 2/4: К чему привязать заметку?",
        "items": NOTE_ENTITY_TYPES,
    }


async def get_entity_options(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for entity selection — fetches recent leads or contacts from Kommo."""
    kommo = dialog_manager.middleware_data.get("kommo_client")
    data = dialog_manager.dialog_data
    entity_type = data.get("entity_type", "leads")

    entity_items: list[tuple[str, str]] = []

    if kommo is not None:
        try:
            if entity_type == "leads":
                entities = await kommo.search_leads(query="", limit=10)
                for e in entities[:10]:
                    label = f"#{e.id} {e.name or '—'}"
                    entity_items.append((label, str(e.id)))
            elif entity_type == "contacts":
                contacts = await kommo.get_contacts(query="")
                for c in contacts[:10]:
                    full_name = " ".join(p for p in [c.first_name, c.last_name] if p) or f"#{c.id}"
                    entity_items.append((full_name, str(c.id)))
        except Exception:
            logger.exception("Failed to fetch entities for note wizard")

    if not entity_items:
        entity_items = [("— нет доступных записей —", "0")]

    entity_label = "сделку" if entity_type == "leads" else "контакт"
    return {
        "title": f"📝 Создание заметки\n\nШаг 3/4: Выберите {entity_label}:",
        "items": entity_items,
    }


async def get_note_summary(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, str]:
    """Getter for summary/confirmation window."""
    data = dialog_manager.dialog_data
    note_text = data.get("note_text", "—")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")

    summary = build_note_summary(
        text=note_text,
        entity_type=entity_type if entity_type != "none" else None,
        entity_id=int(entity_id) if entity_id and str(entity_id) != "0" else None,
    )
    return {"summary": summary}


# --- Handlers ---


async def on_note_text_entered(
    message: Message,
    widget: ManagedTextInput,
    manager: DialogManager,
    value: str,
) -> None:
    """Save note text and advance to entity type selection."""
    manager.dialog_data["note_text"] = value.strip()
    await manager.switch_to(CreateNoteSG.entity_type)


async def on_entity_type_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save entity type — skip entity selection if 'none'."""
    manager.dialog_data["entity_type"] = item_id
    if item_id == "none":
        # Skip entity ID step — go straight to summary
        manager.dialog_data["entity_id"] = None
        await manager.switch_to(CreateNoteSG.summary)
    else:
        await manager.switch_to(CreateNoteSG.entity_id)


async def on_entity_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save entity ID and advance to summary."""
    manager.dialog_data["entity_id"] = item_id
    await manager.switch_to(CreateNoteSG.summary)


async def on_note_confirm(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Create note via Kommo API and close dialog."""
    kommo = manager.middleware_data.get("kommo_client")
    data = manager.dialog_data

    note_text = data.get("note_text", "")
    entity_type = data.get("entity_type")
    entity_id_raw = data.get("entity_id")

    if entity_type == "none" or entity_type is None:
        # No entity attachment — show confirmation without API call
        await callback.answer(
            "📝 Заметка сохранена (без привязки к сделке/контакту)", show_alert=True
        )
        await manager.done()
        return

    if kommo is None:
        await callback.answer("CRM недоступен", show_alert=True)
        await manager.done()
        return

    if not note_text or not entity_id_raw or str(entity_id_raw) == "0":
        await callback.answer("Ошибка: не все поля заполнены", show_alert=True)
        return

    try:
        entity_id = int(entity_id_raw)
        note = await kommo.add_note(entity_type, entity_id, note_text)
        await callback.answer(f"📝 Заметка #{note.id} создана!", show_alert=True)
    except Exception:
        logger.exception("Failed to create note via Kommo")
        await callback.answer("❌ Ошибка при создании заметки", show_alert=True)

    await manager.done()


# --- Dialog ---


create_note_dialog = Dialog(
    # Step 1: Note text input
    Window(
        Format("{title}"),
        TextInput(
            id="note_text_input",
            on_success=on_note_text_entered,
        ),
        Cancel(Const("← Отмена")),
        getter=get_note_text_data,
        state=CreateNoteSG.text,
    ),
    # Step 2: Entity type selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="entity_type_select",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_entity_type_selected,
            ),
        ),
        Back(Const("← Назад")),
        getter=get_entity_type_options,
        state=CreateNoteSG.entity_type,
    ),
    # Step 3: Entity selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="entity_select",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_entity_selected,
            ),
        ),
        Back(Const("← Назад")),
        getter=get_entity_options,
        state=CreateNoteSG.entity_id,
    ),
    # Step 4: Summary / confirmation
    Window(
        Format("{summary}"),
        Button(Const("✅ Сохранить"), id="confirm_note", on_click=on_note_confirm),
        Back(Const("← Изменить")),
        Cancel(Const("✖ Отмена")),
        getter=get_note_summary,
        state=CreateNoteSG.summary,
    ),
)
