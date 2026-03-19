"""Shared catalog runtime helpers for dialog-owned catalog flows."""

from __future__ import annotations

from typing import Any, TypedDict


CATALOG_RUNTIME_DATA_KEY = "catalog_runtime"


class CatalogRuntime(TypedDict, total=False):
    query: str
    source: str
    filters: dict[str, Any]
    view_mode: str
    results: list[dict[str, Any]]
    total: int
    shown_count: int
    next_offset: float | None
    shown_item_ids: list[str]
    current_item_id: str | None
    bookmarks_context: bool
    origin_context: dict[str, Any]


def _dedupe_ids(item_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item_id in item_ids:
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        ordered.append(item_id)
    return ordered


def _extract_result_ids(results: list[dict[str, Any]]) -> list[str]:
    return [str(result["id"]) for result in results if result.get("id") is not None]


def _merge_result_items(
    existing: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []

    for item in [*existing, *extra]:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        item_key = str(item_id) if item_id is not None else ""
        if item_key and item_key in seen_ids:
            continue
        if item_key:
            seen_ids.add(item_key)
        merged.append(item)

    return merged


def build_catalog_runtime(
    *,
    query: str,
    source: str,
    filters: dict[str, Any] | None = None,
    view_mode: str = "cards",
    results: list[dict[str, Any]] | None = None,
    total: int = 0,
    next_offset: float | None = None,
    shown_item_ids: list[str] | None = None,
    current_item_id: str | None = None,
    bookmarks_context: bool = False,
    origin_context: dict[str, Any] | None = None,
) -> CatalogRuntime:
    result_items = results or []
    visible_ids = shown_item_ids or _extract_result_ids(result_items)
    deduped_ids = _dedupe_ids(visible_ids)
    shown_count = len(result_items) if result_items else len(visible_ids)

    runtime: CatalogRuntime = {
        "query": query,
        "source": source,
        "filters": dict(filters or {}),
        "view_mode": view_mode,
        "results": [item for item in result_items if isinstance(item, dict)],
        "total": total,
        "shown_count": shown_count,
        "next_offset": next_offset,
        "shown_item_ids": deduped_ids,
        "current_item_id": current_item_id,
        "bookmarks_context": bookmarks_context,
        "origin_context": dict(origin_context or {}),
    }
    return runtime


def update_catalog_runtime_page(
    runtime: CatalogRuntime,
    *,
    results: list[dict[str, Any]] | None = None,
    total: int | None = None,
    next_offset: float | None = None,
    shown_item_ids: list[str] | None = None,
    current_item_id: str | None = None,
) -> CatalogRuntime:
    updated: CatalogRuntime = dict(runtime)
    existing_results = updated.get("results") or []
    merged_results = _merge_result_items(
        [item for item in existing_results if isinstance(item, dict)],
        [item for item in (results or []) if isinstance(item, dict)],
    )
    new_ids = shown_item_ids or _extract_result_ids(results or [])
    merged_ids = _dedupe_ids([*(updated.get("shown_item_ids") or []), *new_ids])
    page_count = len(results or []) if results is not None else len(new_ids)

    updated["results"] = merged_results
    updated["shown_item_ids"] = merged_ids
    updated["shown_count"] = int(updated.get("shown_count", 0) or 0) + page_count

    if total is not None:
        updated["total"] = total
    updated["next_offset"] = next_offset
    if current_item_id is not None or "current_item_id" in updated:
        updated["current_item_id"] = current_item_id

    return updated
