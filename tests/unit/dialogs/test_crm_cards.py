"""Unit tests for telegram_bot/dialogs/crm_cards.py."""

from __future__ import annotations

from telegram_bot.dialogs.crm_cards import (
    build_pagination_buttons,
    format_contact_card,
    format_lead_card,
    format_task_card,
)
from telegram_bot.services.kommo_models import Contact, Lead, Task


# ---------------------------------------------------------------------------
# format_lead_card
# ---------------------------------------------------------------------------


class TestFormatLeadCard:
    def _make_lead(self, **kwargs) -> Lead:
        defaults = {"id": 1, "name": "Test Lead"}
        return Lead(**(defaults | kwargs))

    def test_contains_lead_id(self) -> None:
        text, _ = format_lead_card(self._make_lead(id=42))
        assert "#42" in text

    def test_contains_lead_name(self) -> None:
        text, _ = format_lead_card(self._make_lead(name="My Deal"))
        assert "My Deal" in text

    def test_budget_formatted(self) -> None:
        text, _ = format_lead_card(self._make_lead(budget=100000))
        assert "€" in text

    def test_budget_none_shows_not_specified(self) -> None:
        text, _ = format_lead_card(self._make_lead(budget=None))
        assert "не указан" in text

    def test_task_count_shown(self) -> None:
        text, _ = format_lead_card(self._make_lead(), task_count=5)
        assert "5" in text

    def test_contact_name_shown(self) -> None:
        lead = self._make_lead(contacts=[{"name": "John Smith"}])
        text, _ = format_lead_card(lead)
        assert "John Smith" in text

    def test_keyboard_has_four_buttons(self) -> None:
        _, keyboard = format_lead_card(self._make_lead())
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) == 4

    def test_keyboard_callback_contains_lead_id(self) -> None:
        _, keyboard = format_lead_card(self._make_lead(id=7))
        all_callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        assert any("7" in (cb or "") for cb in all_callbacks)


# ---------------------------------------------------------------------------
# format_contact_card
# ---------------------------------------------------------------------------


class TestFormatContactCard:
    def _make_contact(self, **kwargs) -> Contact:
        defaults = {"id": 10}
        return Contact(**(defaults | kwargs))

    def test_contains_contact_id(self) -> None:
        text, _ = format_contact_card(self._make_contact(id=10))
        assert "#10" in text

    def test_full_name_shown(self) -> None:
        text, _ = format_contact_card(self._make_contact(first_name="Jane", last_name="Doe"))
        assert "Jane Doe" in text

    def test_only_first_name(self) -> None:
        text, _ = format_contact_card(self._make_contact(first_name="Alice"))
        assert "Alice" in text

    def test_no_name_shows_dash(self) -> None:
        text, _ = format_contact_card(self._make_contact())
        assert "—" in text

    def test_keyboard_has_two_buttons(self) -> None:
        _, keyboard = format_contact_card(self._make_contact())
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) == 2

    def test_created_at_shown(self) -> None:
        text, _ = format_contact_card(self._make_contact(created_at=1700000000))
        assert "Создан:" in text


# ---------------------------------------------------------------------------
# format_task_card
# ---------------------------------------------------------------------------


class TestFormatTaskCard:
    def _make_task(self, **kwargs) -> Task:
        defaults = {"id": 100, "is_completed": False}
        return Task(**(defaults | kwargs))

    def test_contains_task_id(self) -> None:
        text, _ = format_task_card(self._make_task(id=100))
        assert "#100" in text

    def test_incomplete_task_shows_checkbox(self) -> None:
        text, _ = format_task_card(self._make_task(is_completed=False))
        assert "🔲" in text

    def test_completed_task_shows_checkmark(self) -> None:
        text, _ = format_task_card(self._make_task(is_completed=True))
        assert "✅" in text

    def test_task_text_shown(self) -> None:
        text, _ = format_task_card(self._make_task(text="Call client"))
        assert "Call client" in text

    def test_no_text_shows_dash(self) -> None:
        text, _ = format_task_card(self._make_task(text=None))
        assert "—" in text

    def test_due_date_shown(self) -> None:
        text, _ = format_task_card(self._make_task(complete_till=1700000000))
        assert "Срок:" in text

    def test_entity_shown_when_present(self) -> None:
        text, _ = format_task_card(self._make_task(entity_id=5, entity_type="leads"))
        assert "leads" in text
        assert "5" in text

    def test_incomplete_task_has_three_buttons(self) -> None:
        _, keyboard = format_task_card(self._make_task(is_completed=False))
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) == 3

    def test_completed_task_has_one_button(self) -> None:
        _, keyboard = format_task_card(self._make_task(is_completed=True))
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(all_buttons) == 1


# ---------------------------------------------------------------------------
# build_pagination_buttons
# ---------------------------------------------------------------------------


class TestBuildPaginationButtons:
    def test_first_page_no_prev_button(self) -> None:
        buttons = build_pagination_buttons(prefix="p", page=0, total=20)
        texts = [b.text for b in buttons]
        assert not any("Назад" in t for t in texts)

    def test_first_page_has_next_when_more_items(self) -> None:
        buttons = build_pagination_buttons(prefix="p", page=0, total=20, page_size=5)
        texts = [b.text for b in buttons]
        assert any("Вперёд" in t for t in texts)

    def test_last_page_no_next_button(self) -> None:
        buttons = build_pagination_buttons(prefix="p", page=3, total=20, page_size=5)
        texts = [b.text for b in buttons]
        assert not any("Вперёд" in t for t in texts)

    def test_middle_page_has_both_buttons(self) -> None:
        buttons = build_pagination_buttons(prefix="p", page=1, total=20, page_size=5)
        assert len(buttons) == 2

    def test_callback_data_contains_prefix_and_page(self) -> None:
        buttons = build_pagination_buttons(prefix="crm:lead:page", page=2, total=30, page_size=5)
        callbacks = [b.callback_data for b in buttons]
        assert any("crm:lead:page:1" in (c or "") for c in callbacks)
        assert any("crm:lead:page:3" in (c or "") for c in callbacks)

    def test_single_page_no_buttons(self) -> None:
        buttons = build_pagination_buttons(prefix="p", page=0, total=3, page_size=5)
        assert buttons == []
