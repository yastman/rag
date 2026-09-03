"""ApartmentCatalog — one application interface for demo and catalog search (#3238).

Single owner of the query-to-page contract that the demo dialog and the
production catalog dialog previously duplicated across each other:

* regex-first extraction with optional structured gap-fill
  (:class:`~telegram_bot.services.apartment.apartment_extraction_pipeline.ApartmentExtractionPipeline`);
* Qdrant payload filtering with price ordering
  (:meth:`~telegram_bot.services.apartment.apartments_service.ApartmentsService.scroll_with_filters`);
* cursor/continuation paging (price-ordered ``next_offset`` plus shown-id
  deduplication);
* a well-formed empty page when the catalog service is unavailable.

Transport dialogs (demo, catalog, funnel, filter) only map a
:class:`CatalogPage` onto catalog runtime and rendering, so every entrypoint
produces identical results and navigation from the same query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.models.apartment import ApartmentSearchFilters


if TYPE_CHECKING:  # pragma: no cover
    from telegram_bot.services.apartment.apartment_extraction_pipeline import (
        ApartmentExtractionPipeline,
    )
    from telegram_bot.services.apartment.apartments_service import ApartmentsService


DEFAULT_PAGE_SIZE = 10


@dataclass(frozen=True)
class CatalogPage:
    """One price-ordered result page plus its continuation cursor."""

    query: str
    filters: dict[str, Any]
    results: list[dict[str, Any]]
    total: int
    next_offset: float | None
    shown_item_ids: list[str]

    @property
    def is_empty(self) -> bool:
        """No-result flag: the page carries zero matching apartments."""
        return not self.results


class ApartmentCatalog:
    """Application-facing apartment catalog contract shared by all entrypoints.

    Composes the extraction pipeline and the Qdrant-backed apartments
    service into one interface; callers never touch either dependency
    directly, which keeps extraction, filtering, price order, paging and
    no-result behavior in one place (#3238).
    """

    DEFAULT_PAGE_SIZE = DEFAULT_PAGE_SIZE

    def __init__(
        self,
        extraction_pipeline: ApartmentExtractionPipeline | None = None,
        apartments_service: ApartmentsService | None = None,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._pipeline = extraction_pipeline
        self._service = apartments_service
        self._page_size = page_size

    # -- construction -------------------------------------------------------

    @classmethod
    def from_dialog_manager(cls, dialog_manager: Any) -> ApartmentCatalog:
        """Build the catalog from aiogram-dialog middleware data."""
        middleware = getattr(dialog_manager, "middleware_data", None) or {}
        pipeline = middleware.get("pipeline")
        service = middleware.get("apartments_service")
        if service is None:
            property_bot = middleware.get("property_bot")
            if property_bot is not None:
                service = getattr(property_bot, "_apartments_service", None)
        return cls(extraction_pipeline=pipeline, apartments_service=service)

    # -- capabilities -------------------------------------------------------

    @property
    def extraction_available(self) -> bool:
        return self._pipeline is not None

    @property
    def service_available(self) -> bool:
        return self._service is not None

    # -- contract -----------------------------------------------------------

    async def extract(self, query: str) -> ApartmentSearchFilters | None:
        """Regex-first extraction with optional structured gap-fill.

        Returns ``None`` when no extraction pipeline is wired (transport
        decides how to degrade).
        """
        if self._pipeline is None:
            return None
        return await self._pipeline.extract(query)

    async def extract_filters(self, query: str) -> dict[str, Any]:
        """Hard Qdrant payload filters for a free-text query."""
        extraction = await self.extract(query)
        if extraction is None:
            return {}
        return extraction.hard.to_filters_dict() or {}

    async def search(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> CatalogPage:
        """First page for a query; extracts filters when not supplied."""
        if filters is None:
            filters = await self.extract_filters(query)
        return await self.fetch_page(query=query, filters=filters)

    async def continue_page(
        self,
        *,
        query: str,
        filters: dict[str, Any] | None,
        next_offset: float | None,
        shown_item_ids: list[str],
    ) -> CatalogPage:
        """Next page from a stored cursor/continuation."""
        return await self.fetch_page(
            query=query,
            filters=filters,
            start_from=next_offset,
            exclude_ids=list(shown_item_ids) if shown_item_ids else None,
        )

    async def fetch_page(
        self,
        *,
        query: str,
        filters: dict[str, Any] | None,
        start_from: float | None = None,
        exclude_ids: list[str] | None = None,
    ) -> CatalogPage:
        """One price-ordered payload page from the catalog service.

        Without a wired service this returns a well-formed empty page so
        callers keep a single no-result code path.
        """
        if self._service is None:
            return CatalogPage(
                query=query,
                filters=dict(filters or {}),
                results=[],
                total=0,
                next_offset=None,
                shown_item_ids=[],
            )
        results, total, next_offset, page_ids = await self._service.scroll_with_filters(
            filters=filters or None,
            limit=self._page_size,
            start_from=start_from,
            exclude_ids=exclude_ids,
        )
        return CatalogPage(
            query=query,
            filters=dict(filters or {}),
            results=results,
            total=total,
            next_offset=next_offset,
            shown_item_ids=list(page_ids),
        )


__all__ = ["DEFAULT_PAGE_SIZE", "ApartmentCatalog", "CatalogPage"]
