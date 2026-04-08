"""Contracts for the shared catalog runtime."""

from telegram_bot.services.catalog_session import (
    build_catalog_runtime,
    clear_legacy_catalog_state,
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


def test_clear_legacy_catalog_state_removes_parallel_browsing_keys() -> None:
    cleaned = clear_legacy_catalog_state(
        {
            "catalog_runtime": {"query": "двушка", "results": [{"id": "apt-1"}]},
            "apartment_results": [{"id": "legacy"}],
            "apartment_offset": 10,
            "apartment_total": 42,
            "apartment_next_offset": "cursor",
            "apartment_filters": {"rooms": 2},
            "apartment_footer_msg_id": 777,
            "bookmark_message_ids": [100],
        }
    )

    assert cleaned["catalog_runtime"]["query"] == "двушка"
    assert "apartment_results" not in cleaned
    assert "apartment_offset" not in cleaned
    assert "apartment_total" not in cleaned
    assert "apartment_next_offset" not in cleaned
    assert "apartment_filters" not in cleaned
    assert "apartment_footer_msg_id" not in cleaned
    assert cleaned["bookmark_message_ids"] == [100]


def test_clear_legacy_catalog_state_keeps_unrelated_keys() -> None:
    cleaned = clear_legacy_catalog_state(
        {
            "catalog_runtime": {"source": "free_text"},
            "bookmark_message_ids": [55],
            "other_key": "keep-me",
        }
    )

    assert cleaned["catalog_runtime"]["source"] == "free_text"
    assert cleaned["bookmark_message_ids"] == [55]
    assert cleaned["other_key"] == "keep-me"
