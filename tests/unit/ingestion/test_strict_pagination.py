"""Ingestion must fully paginate collections created by production bootstrap."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.ingestion.unified.flow import _file_ids_for_source
from src.runtime.qdrant.contracts import STRICT_MODE_LIMITS


def strict_pages(records):
    offsets = []

    def scroll(**kwargs):
        limit = kwargs["limit"]
        assert 0 < limit <= STRICT_MODE_LIMITS["max_query_limit"], "strict query limit exceeded"
        offset = kwargs["offset"]
        offsets.append(offset)
        start = 0 if offset is None else offset
        end = start + limit
        return records[start:end], end if end < len(records) else None

    return scroll, offsets


def test_prewrite_source_scan_collects_file_ids_across_strict_pages():
    count = STRICT_MODE_LIMITS["max_query_limit"] * 2 + 5
    records = [
        SimpleNamespace(payload={"metadata": {"file_id": f"file-{i}"}}) for i in range(count)
    ]
    scroll, offsets = strict_pages(records)
    client = MagicMock(scroll=MagicMock(side_effect=scroll))
    assert _file_ids_for_source(client, "owned_collection", "alpha.md") == {
        f"file-{i}" for i in range(count)
    }
    assert len(offsets) == 3
    for call in client.scroll.call_args_list:
        assert call.kwargs["scroll_filter"].must[0].match.value == "alpha.md"


def test_stale_sweep_paginates_all_ids_and_preserves_new_generation(writer, mock_qdrant_client):
    old_ids = {f"old-{i}" for i in range(STRICT_MODE_LIMITS["max_query_limit"] * 2 + 5)}
    new_ids = {"new-1", "new-2"}
    scroll, offsets = strict_pages(
        [SimpleNamespace(id=value) for value in sorted(old_ids | new_ids)]
    )

    def before_delete(**kwargs):
        mock_qdrant_client.delete.assert_not_called()
        return scroll(**kwargs)

    mock_qdrant_client.scroll.side_effect = before_delete
    assert writer._delete_stale_points_sync(
        file_id="source-id", collection_name="owned_collection", new_ids=new_ids
    ) == len(old_ids)
    assert len(offsets) == 3
    mock_qdrant_client.delete.assert_called_once()
    selector = mock_qdrant_client.delete.call_args.kwargs["points_selector"]
    assert set(selector.must[0].has_id) == old_ids
    assert not set(selector.must[0].has_id) & new_ids


def test_zero_point_offset_does_not_end_stale_sweep(writer, mock_qdrant_client):
    mock_qdrant_client.scroll.side_effect = [
        ([SimpleNamespace(id="new")], 0),
        ([SimpleNamespace(id="old")], None),
    ]
    assert (
        writer._delete_stale_points_sync(
            file_id="source-id", collection_name="owned_collection", new_ids={"new"}
        )
        == 1
    )
    assert mock_qdrant_client.scroll.call_args_list[1].kwargs["offset"] == 0


def test_failed_later_page_never_deletes_a_partial_stale_set(writer, mock_qdrant_client):
    mock_qdrant_client.scroll.side_effect = [
        ([SimpleNamespace(id="old")], "next-page"),
        RuntimeError("page unavailable"),
    ]
    with pytest.raises(RuntimeError, match="page unavailable"):
        writer._delete_stale_points_sync(
            file_id="source-id", collection_name="owned_collection", new_ids={"new"}
        )
    mock_qdrant_client.delete.assert_not_called()
