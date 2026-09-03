"""Unit tests for the shared ApartmentCatalog application interface (#3238)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _extraction(filters: dict | None = None) -> SimpleNamespace:
    hard_filters = filters or {"rooms": 2}

    def _to_filters_dict() -> dict:
        return dict(hard_filters)

    return SimpleNamespace(hard=SimpleNamespace(to_filters_dict=_to_filters_dict))


def _make_pipeline(extraction: object | None = None) -> AsyncMock:
    pipeline = AsyncMock()
    pipeline.extract = AsyncMock(return_value=extraction or _extraction())
    return pipeline


def _make_svc(
    results: list | None = None,
    total: int = 42,
    next_offset: float | None = 80000.0,
    page_ids: list[str] | None = None,
) -> MagicMock:
    svc = MagicMock()
    svc.scroll_with_filters = AsyncMock(
        return_value=(results or [{"id": "apt-1"}], total, next_offset, page_ids or ["apt-1"])
    )
    return svc


@pytest.mark.asyncio
async def test_search_extracts_then_scrolls_first_page() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    pipeline = _make_pipeline()
    svc = _make_svc(results=[{"id": "apt-1"}] * 10, total=42, next_offset=75000.0)
    catalog = ApartmentCatalog(extraction_pipeline=pipeline, apartments_service=svc)

    page = await catalog.search("двушка до 100к")

    pipeline.extract.assert_awaited_once_with("двушка до 100к")
    svc.scroll_with_filters.assert_awaited_once_with(
        filters={"rooms": 2},
        limit=10,
        start_from=None,
        exclude_ids=None,
    )
    assert page.total == 42
    assert page.next_offset == 75000.0
    assert page.shown_item_ids == ["apt-1"]
    assert not page.is_empty


@pytest.mark.asyncio
async def test_search_with_explicit_filters_skips_extraction() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    pipeline = _make_pipeline()
    svc = _make_svc()
    catalog = ApartmentCatalog(extraction_pipeline=pipeline, apartments_service=svc)

    await catalog.search("anything", filters={"city": "Варна"})

    pipeline.extract.assert_not_awaited()
    assert svc.scroll_with_filters.await_args.kwargs["filters"] == {"city": "Варна"}


@pytest.mark.asyncio
async def test_continue_page_passes_cursor_and_shown_ids() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    svc = _make_svc(results=[{"id": "apt-2"}], total=42, next_offset=90000.0, page_ids=["apt-2"])
    catalog = ApartmentCatalog(apartments_service=svc)

    page = await catalog.continue_page(
        query="двушка",
        filters={"rooms": 2},
        next_offset=75000.0,
        shown_item_ids=["apt-1"],
    )

    svc.scroll_with_filters.assert_awaited_once_with(
        filters={"rooms": 2},
        limit=10,
        start_from=75000.0,
        exclude_ids=["apt-1"],
    )
    assert page.next_offset == 90000.0


@pytest.mark.asyncio
async def test_no_service_yields_well_formed_empty_page() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    catalog = ApartmentCatalog(extraction_pipeline=_make_pipeline(), apartments_service=None)

    page = await catalog.search("двушка")

    assert page.is_empty
    assert page.total == 0
    assert page.results == []
    assert page.next_offset is None


@pytest.mark.asyncio
async def test_extract_returns_none_without_pipeline() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    catalog = ApartmentCatalog(extraction_pipeline=None, apartments_service=_make_svc())

    assert catalog.extraction_available is False
    assert await catalog.extract("двушка") is None
    assert await catalog.extract_filters("двушка") == {}


def test_from_dialog_manager_prefers_service_and_falls_back_to_property_bot() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    svc = _make_svc()
    manager = MagicMock()
    manager.middleware_data = {
        "pipeline": _make_pipeline(),
        "apartments_service": svc,
    }
    catalog = ApartmentCatalog.from_dialog_manager(manager)
    assert catalog.service_available is True
    assert catalog._service is svc

    fallback_bot = MagicMock()
    fallback_bot._apartments_service = svc
    manager2 = MagicMock()
    manager2.middleware_data = {"property_bot": fallback_bot}
    catalog2 = ApartmentCatalog.from_dialog_manager(manager2)
    assert catalog2.service_available is True


def test_from_dialog_manager_without_dependencies() -> None:
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog

    manager = MagicMock()
    manager.middleware_data = {}
    catalog = ApartmentCatalog.from_dialog_manager(manager)

    assert catalog.extraction_available is False
    assert catalog.service_available is False


@pytest.mark.asyncio
async def test_real_extraction_pipeline_integration() -> None:
    """The interface accepts the production regex-first extraction pipeline."""
    from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog
    from telegram_bot.services.apartment.apartment_extraction_pipeline import (
        ApartmentExtractionPipeline,
    )
    from telegram_bot.services.apartment.apartment_filter_extractor import ApartmentFilterExtractor

    catalog = ApartmentCatalog(
        extraction_pipeline=ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
        ),
        apartments_service=_make_svc(),
    )

    filters = await catalog.extract_filters("двушка до 100000 евро")

    # Repo convention (#959 parametrized tests): "двушка" → rooms=3, price cap parsed.
    assert filters.get("rooms") == 3
    assert filters.get("price_eur") == {"lte": 100000.0}
