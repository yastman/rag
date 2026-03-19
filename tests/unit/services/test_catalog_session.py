"""Contracts for the shared catalog runtime."""

from telegram_bot.services.catalog_session import (
    build_catalog_runtime,
    update_catalog_runtime_page,
)


def test_build_catalog_runtime_sets_expected_defaults() -> None:
    runtime = build_catalog_runtime(
        query="funnel:varna",
        source="funnel",
        filters={"city": "varna"},
        view_mode="cards",
        results=[{"id": "a1"}, {"id": "a2"}],
        total=24,
        next_offset=10,
        shown_item_ids=["a1", "a2"],
    )

    assert runtime["query"] == "funnel:varna"
    assert runtime["source"] == "funnel"
    assert runtime["filters"] == {"city": "varna"}
    assert runtime["view_mode"] == "cards"
    assert [item["id"] for item in runtime["results"]] == ["a1", "a2"]
    assert runtime["shown_count"] == 2
    assert runtime["total"] == 24
    assert runtime["next_offset"] == 10


def test_update_catalog_runtime_page_accumulates_shown_ids() -> None:
    runtime = {
        "results": [{"id": "a1"}, {"id": "a2"}],
        "shown_count": 2,
        "shown_item_ids": ["a1", "a2"],
        "total": 24,
        "next_offset": 10,
    }

    updated = update_catalog_runtime_page(
        runtime,
        results=[{"id": "a3"}, {"id": "a4"}],
        total=24,
        next_offset=20,
        shown_item_ids=["a3", "a4"],
    )

    assert updated["shown_count"] == 4
    assert updated["shown_item_ids"] == ["a1", "a2", "a3", "a4"]
    assert [item["id"] for item in updated["results"]] == ["a1", "a2", "a3", "a4"]
    assert updated["next_offset"] == 20


def test_catalog_states_exist() -> None:
    from telegram_bot.dialogs.states import CatalogSG

    assert hasattr(CatalogSG, "results")
    assert hasattr(CatalogSG, "empty")
    assert hasattr(CatalogSG, "details")
