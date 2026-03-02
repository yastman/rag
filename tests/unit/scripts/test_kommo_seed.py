"""Unit tests for Kommo CRM seeder."""

from __future__ import annotations

import random

import pytest


def test_parse_args_defaults():
    """CLI defaults: 30 contacts, 50 leads, dry-run off."""
    from scripts.kommo_seed import parse_args

    args = parse_args([])
    assert args.contacts == 30
    assert args.leads == 50
    assert args.dry_run is False
    assert args.pipeline_id is None


def test_parse_args_custom():
    """CLI accepts custom values."""
    from scripts.kommo_seed import parse_args

    args = parse_args(["--contacts", "10", "--leads", "20", "--dry-run", "--pipeline-id", "999"])
    assert args.contacts == 10
    assert args.leads == 20
    assert args.dry_run is True
    assert args.pipeline_id == 999


def test_generate_contact_data():
    """Contact data has valid first_name, last_name, phone."""
    from scripts.kommo_seed import generate_contact_data

    random.seed(42)
    contact = generate_contact_data(index=0)
    assert contact["first_name"]
    assert contact["last_name"]
    assert contact["phone"].startswith("+")
    assert len(contact["phone"]) >= 10


def test_scenarios_cover_all_services():
    """Scenarios cover all 6 service types."""
    from scripts.kommo_seed import SCENARIOS

    titles = {s.service_key for s in SCENARIOS}
    assert "apartment_search" in titles
    assert "viewing" in titles
    assert "infotour" in titles
    assert "installment" in titles
    assert "vnzh" in titles
    assert "passive_income" in titles


def test_pick_scenario_returns_scenario():
    """pick_scenario returns a Scenario dataclass."""
    from scripts.kommo_seed import SCENARIOS, pick_scenario

    random.seed(42)
    s = pick_scenario()
    assert s in SCENARIOS
    assert s.crm_title
    assert s.note_templates


def test_fetch_apartments_from_qdrant():
    """fetch_apartments scrolls Qdrant and returns apartment dicts."""
    from unittest.mock import MagicMock

    from scripts.kommo_seed import fetch_apartments

    mock_record = MagicMock()
    mock_record.payload = {
        "complex_name": "Premier Fort Beach",
        "rooms": 2,
        "price_eur": 75000,
        "area_m2": 65.0,
        "floor": 3,
        "floor_label": "3",
        "view_primary": "sea",
        "apartment_number": "A-301",
        "city": "Sunny Beach",
    }

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([mock_record], None)

    apartments = fetch_apartments(mock_client, collection="apartments", limit=30)
    assert len(apartments) == 1
    assert apartments[0]["complex_name"] == "Premier Fort Beach"
    assert apartments[0]["price_eur"] == 75000
    mock_client.scroll.assert_called_once()


def test_distribute_statuses():
    """Leads distributed across funnel stages with correct proportions."""
    from scripts.kommo_seed import distribute_statuses

    statuses = {
        "new": 100,
        "qualified": 101,
        "negotiation": 102,
        "proposal": 103,
        "won": 142,
        "lost": 143,
    }
    result = distribute_statuses(50, statuses)
    assert len(result) == 50
    # Check rough proportions (30% new = ~15)
    new_count = sum(1 for s in result if s == 100)
    assert 10 <= new_count <= 20  # ~30% of 50


def test_distribute_statuses_ignores_non_positive_status_ids():
    """0/-1 placeholders are ignored and fallback is None when no valid IDs exist."""
    from scripts.kommo_seed import distribute_statuses

    statuses = {
        "new": 0,
        "qualified": -1,
        "negotiation": 0,
        "proposal": 0,
        "won": 0,
        "lost": 0,
    }
    result = distribute_statuses(4, statuses)
    assert result == [None, None, None, None]


def test_build_lead_data():
    """build_lead_data creates LeadCreate-compatible dict."""
    from scripts.kommo_seed import Scenario, build_lead_data

    apartment = {
        "complex_name": "Premier Fort Beach",
        "rooms": 2,
        "price_eur": 75000,
        "area_m2": 65.0,
        "floor": 3,
        "floor_label": "3",
        "view_primary": "sea",
        "apartment_number": "A-301",
    }
    scenario = Scenario(
        service_key="apartment_search",
        crm_title="Подбор апартаментов",
        note_templates=["Клиент интересуется {complex_name}."],
        task_templates=["Перезвонить: {phone} ({name})"],
    )
    contact_name = "Иванов Александр"
    lead = build_lead_data(scenario, apartment, contact_name, status_id=100, pipeline_id=1)
    assert "Premier Fort Beach" in lead["name"]
    assert "Иванов" in lead["name"]
    assert lead["budget"] == 7500000  # price * 100 (cents)
    assert lead["pipeline_id"] == 1
    assert lead["status_id"] == 100


def test_render_note():
    """render_note formats template with apartment + contact data."""
    from scripts.kommo_seed import render_note

    template = "Клиент интересуется {complex_name}. Бюджет: {budget}€. Источник: Telegram бот."
    apartment = {
        "complex_name": "Royal Sun",
        "price_eur": 55000,
        "rooms": 1,
        "area_m2": 42.0,
        "floor": 5,
        "view_primary": "pool",
        "apartment_number": "B-501",
    }
    ctx = {"phone": "+380991234567", "name": "Иванов А.", "budget": 55000}
    result = render_note(template, apartment, ctx)
    assert "Royal Sun" in result
    assert "55000" in result


def test_render_task():
    """render_task formats task template."""
    from scripts.kommo_seed import render_task

    template = "Перезвонить: {phone} ({name}) — подбор апартаментов в {complex_name}"
    apartment = {
        "complex_name": "Grand Fort Noks",
        "apartment_number": "C-102",
        "rooms": 2,
        "price_eur": 80000,
        "area_m2": 70.0,
        "floor": 2,
        "view_primary": "sea",
    }
    ctx = {"phone": "+7999111222", "name": "Петрова М."}
    result = render_task(template, apartment, ctx)
    assert "Петрова М." in result
    assert "Grand Fort Noks" in result


def test_render_installment_note():
    """Installment notes compute deposit and monthly."""
    from scripts.kommo_seed import render_note

    template = (
        "Расчёт рассрочки: {price_eur}€, взнос 10% = {deposit}€, ежемесячно ~{monthly}€ на 36 мес."
    )
    apartment = {
        "complex_name": "X",
        "price_eur": 50000,
        "rooms": 1,
        "area_m2": 38.0,
        "floor": 1,
        "view_primary": "garden",
        "apartment_number": "A-1",
    }
    ctx = {"phone": "+380", "name": "Test", "budget": 50000}
    result = render_note(template, apartment, ctx)
    assert "5000" in result  # 10% deposit
    assert "1250" in result  # (50000-5000)/36


@pytest.mark.asyncio
async def test_seed_dry_run(capsys):
    """Dry-run prints plan without API calls."""
    from scripts.kommo_seed import seed_crm

    apartments = [
        {
            "complex_name": "Test Complex",
            "rooms": 1,
            "price_eur": 40000,
            "area_m2": 38.0,
            "floor": 2,
            "view_primary": "garden",
            "apartment_number": "T-101",
            "city": "Sunny Beach",
        },
        {
            "complex_name": "Beach Resort",
            "rooms": 2,
            "price_eur": 65000,
            "area_m2": 55.0,
            "floor": 4,
            "view_primary": "sea",
            "apartment_number": "B-401",
            "city": "Sveti Vlas",
        },
    ]
    statuses = {
        "new": 100,
        "qualified": 101,
        "negotiation": 102,
        "proposal": 103,
        "won": 142,
        "lost": 143,
    }

    stats = await seed_crm(
        kommo_client=None,
        apartments=apartments,
        statuses=statuses,
        pipeline_id=1,
        num_contacts=3,
        num_leads=5,
        dry_run=True,
    )
    assert stats["contacts_created"] == 3
    assert stats["leads_created"] == 5
    assert stats["api_calls"] == 0  # dry-run = 0 API calls


@pytest.mark.asyncio
async def test_seed_dry_run_rejects_leads_without_contacts():
    """When leads are requested, zero contacts should fail fast with a clear error."""
    from scripts.kommo_seed import seed_crm

    apartments = [
        {
            "complex_name": "Test Complex",
            "rooms": 1,
            "price_eur": 40000,
            "area_m2": 38.0,
            "floor": 2,
            "view_primary": "garden",
            "apartment_number": "T-101",
            "city": "Sunny Beach",
        }
    ]
    statuses = {"new": 100}

    with pytest.raises(ValueError, match="num_contacts must be > 0"):
        await seed_crm(
            kommo_client=None,
            apartments=apartments,
            statuses=statuses,
            pipeline_id=1,
            num_contacts=0,
            num_leads=1,
            dry_run=True,
        )


@pytest.mark.asyncio
async def test_seed_dry_run_full_flow():
    """Full dry-run: generates contacts, leads with notes and tasks."""
    from scripts.kommo_seed import seed_crm

    apartments = [
        {
            "complex_name": "Premier Fort Beach",
            "rooms": 2,
            "price_eur": 75000,
            "area_m2": 65.0,
            "floor": 3,
            "view_primary": "sea",
            "apartment_number": "A-301",
            "city": "Sunny Beach",
            "floor_label": "3",
        },
        {
            "complex_name": "Grand Fort Noks",
            "rooms": 1,
            "price_eur": 45000,
            "area_m2": 38.0,
            "floor": 5,
            "view_primary": "pool",
            "apartment_number": "B-501",
            "city": "Sunny Beach",
            "floor_label": "5",
        },
        {
            "complex_name": "Royal Sun",
            "rooms": 3,
            "price_eur": 120000,
            "area_m2": 95.0,
            "floor": 7,
            "view_primary": "sea",
            "apartment_number": "C-701",
            "city": "Sveti Vlas",
            "floor_label": "7",
        },
    ]
    statuses = {
        "new": 100,
        "qualified": 101,
        "negotiation": 102,
        "proposal": 103,
        "won": 142,
        "lost": 143,
    }

    random.seed(42)
    stats = await seed_crm(
        kommo_client=None,
        apartments=apartments,
        statuses=statuses,
        pipeline_id=1,
        num_contacts=10,
        num_leads=20,
        dry_run=True,
    )

    assert stats["contacts_created"] == 10
    assert stats["leads_created"] == 20
    assert stats["notes_created"] > 0
    assert stats["tasks_created"] > 0
    assert stats["links_created"] == 20
    assert stats["api_calls"] == 0
