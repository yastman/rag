"""Tests for scripts/langfuse_triage.py (TDD red-green-refactor).

Issue #757: auto-triage dislike traces → Annotation Queue "dislike-review"
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def _load_module():
    """Load langfuse_triage as a module without executing main()."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "langfuse_triage.py"
    spec = importlib.util.spec_from_file_location("langfuse_triage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_meta(total_pages: int = 1, page: int = 1) -> SimpleNamespace:
    return SimpleNamespace(total_pages=total_pages, page=page)


# ---------------------------------------------------------------------------
# fetch_dislike_trace_ids
# ---------------------------------------------------------------------------


class TestFetchDislikeTraceIds:
    def test_returns_trace_ids_with_feedback_zero(self):
        """Fetches traces where user_feedback score = 0."""
        module = _load_module()

        score1 = SimpleNamespace(trace_id="trace-aaa", value=0.0)
        score2 = SimpleNamespace(trace_id="trace-bbb", value=0.0)

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(
            data=[score1, score2], meta=_make_meta()
        )

        trace_ids = module.fetch_dislike_trace_ids(mock_api, hours=24)

        assert "trace-aaa" in trace_ids
        assert "trace-bbb" in trace_ids
        assert len(trace_ids) == 2

    def test_calls_score_v2_api_with_correct_params(self):
        """Uses score_v_2 API (not v1 score) with name=user_feedback, value=0."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(data=[], meta=_make_meta())

        module.fetch_dislike_trace_ids(mock_api, hours=24)

        mock_api.score_v_2.get.assert_called_once()
        kwargs = mock_api.score_v_2.get.call_args.kwargs
        assert kwargs.get("name") == "user_feedback"
        assert kwargs.get("value") == 0
        # v1 score.get must NOT be called
        mock_api.score.get.assert_not_called()

    def test_filters_by_time_window(self):
        """from_timestamp is set to now - hours."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(data=[], meta=_make_meta())

        before = datetime.now(UTC)
        module.fetch_dislike_trace_ids(mock_api, hours=24)
        after = datetime.now(UTC)

        kwargs = mock_api.score_v_2.get.call_args.kwargs
        from_ts = kwargs.get("from_timestamp")
        assert from_ts is not None

        expected_lower = before - timedelta(hours=24, seconds=1)
        expected_upper = after - timedelta(hours=24) + timedelta(seconds=1)
        assert expected_lower <= from_ts <= expected_upper

    def test_returns_empty_list_when_no_dislikes(self):
        """Returns empty list if no dislike scores found."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(data=[], meta=_make_meta())

        result = module.fetch_dislike_trace_ids(mock_api, hours=24)
        assert result == []

    def test_deduplicates_trace_ids(self):
        """Multiple scores for same trace yield one trace_id."""
        module = _load_module()

        score1 = SimpleNamespace(trace_id="trace-dup", value=0.0)
        score2 = SimpleNamespace(trace_id="trace-dup", value=0.0)

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(
            data=[score1, score2], meta=_make_meta()
        )

        result = module.fetch_dislike_trace_ids(mock_api, hours=24)
        assert result.count("trace-dup") == 1

    def test_skips_none_trace_ids(self):
        """Scores with trace_id=None are silently skipped."""
        module = _load_module()

        score_none = SimpleNamespace(trace_id=None, value=0.0)
        score_valid = SimpleNamespace(trace_id="trace-ok", value=0.0)

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(
            data=[score_none, score_valid], meta=_make_meta()
        )

        result = module.fetch_dislike_trace_ids(mock_api, hours=24)
        assert result == ["trace-ok"]

    def test_paginates_through_all_pages(self):
        """Fetches all pages when total_pages > 1."""
        module = _load_module()

        score1 = SimpleNamespace(trace_id="t1", value=0.0)
        score2 = SimpleNamespace(trace_id="t2", value=0.0)

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=[score1], meta=_make_meta(total_pages=2, page=1)),
            SimpleNamespace(data=[score2], meta=_make_meta(total_pages=2, page=2)),
        ]

        result = module.fetch_dislike_trace_ids(mock_api, hours=24)

        assert len(result) == 2
        assert mock_api.score_v_2.get.call_count == 2

    def test_stops_pagination_when_data_empty(self):
        """Stops pagination when API returns empty data."""
        module = _load_module()

        score1 = SimpleNamespace(trace_id="t1", value=0.0)

        mock_api = MagicMock()
        mock_api.score_v_2.get.side_effect = [
            SimpleNamespace(data=[score1], meta=_make_meta(total_pages=3, page=1)),
            SimpleNamespace(data=[], meta=_make_meta(total_pages=3, page=2)),
        ]

        result = module.fetch_dislike_trace_ids(mock_api, hours=24)
        assert len(result) == 1
        assert mock_api.score_v_2.get.call_count == 2


# ---------------------------------------------------------------------------
# get_or_create_annotation_queue
# ---------------------------------------------------------------------------


class TestGetOrCreateAnnotationQueue:
    def test_returns_existing_queue_id(self):
        """Returns ID of existing queue without creating a new one."""
        module = _load_module()

        existing_queue = SimpleNamespace(id="queue-111", name="dislike-review")
        mock_api = MagicMock()
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[existing_queue], meta=_make_meta()
        )

        queue_id = module.get_or_create_annotation_queue(mock_api, "dislike-review")

        assert queue_id == "queue-111"
        mock_api.annotation_queues.create_queue.assert_not_called()

    def test_creates_queue_when_not_found(self):
        """Creates queue if it doesn't exist and returns its ID."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[], meta=_make_meta()
        )
        mock_api.annotation_queues.create_queue.return_value = SimpleNamespace(id="queue-new")

        queue_id = module.get_or_create_annotation_queue(mock_api, "dislike-review")

        assert queue_id == "queue-new"
        mock_api.annotation_queues.create_queue.assert_called_once()

    def test_create_queue_called_with_correct_name(self):
        """create_queue is called with the correct queue name."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[], meta=_make_meta()
        )
        mock_api.annotation_queues.create_queue.return_value = SimpleNamespace(id="q-1")

        module.get_or_create_annotation_queue(mock_api, "dislike-review")

        call_kwargs = mock_api.annotation_queues.create_queue.call_args.kwargs
        assert call_kwargs["name"] == "dislike-review"
        assert call_kwargs["score_config_ids"] == []

    def test_returns_correct_queue_among_multiple(self):
        """Finds correct queue when multiple queues exist."""
        module = _load_module()

        queue_a = SimpleNamespace(id="q-a", name="other-queue")
        queue_b = SimpleNamespace(id="q-b", name="dislike-review")
        mock_api = MagicMock()
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[queue_a, queue_b], meta=_make_meta()
        )

        queue_id = module.get_or_create_annotation_queue(mock_api, "dislike-review")

        assert queue_id == "q-b"

    def test_uses_list_queues_not_list(self):
        """Must call list_queues(), not list() (v1 API)."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="q-1", name="dislike-review")], meta=_make_meta()
        )

        module.get_or_create_annotation_queue(mock_api, "dislike-review")

        mock_api.annotation_queues.list_queues.assert_called_once()
        mock_api.annotation_queues.list.assert_not_called()


# ---------------------------------------------------------------------------
# add_traces_to_queue
# ---------------------------------------------------------------------------


class TestAddTracesToQueue:
    def test_adds_each_trace_as_pending_item(self):
        """Each trace is added as a TRACE item to the queue."""
        module = _load_module()

        mock_api = MagicMock()
        trace_ids = ["trace-1", "trace-2", "trace-3"]

        count = module.add_traces_to_queue(mock_api, "queue-xyz", trace_ids)

        assert count == 3
        assert mock_api.annotation_queues.create_queue_item.call_count == 3

    def test_item_uses_trace_object_type(self):
        """objectType must be TRACE (not SESSION due to bug #9571)."""
        module = _load_module()

        mock_api = MagicMock()
        module.add_traces_to_queue(mock_api, "queue-xyz", ["trace-1"])

        call_kwargs = mock_api.annotation_queues.create_queue_item.call_args.kwargs
        assert call_kwargs["object_type"].value == "TRACE"
        assert call_kwargs["status"].value == "PENDING"

    def test_item_object_id_matches_trace_id(self):
        """object_id in request matches the trace ID."""
        module = _load_module()

        mock_api = MagicMock()
        module.add_traces_to_queue(mock_api, "queue-xyz", ["trace-abc-123"])

        call_kwargs = mock_api.annotation_queues.create_queue_item.call_args.kwargs
        assert call_kwargs["object_id"] == "trace-abc-123"

    def test_returns_zero_for_empty_list(self):
        """Returns 0 when no traces to add."""
        module = _load_module()

        mock_api = MagicMock()
        count = module.add_traces_to_queue(mock_api, "queue-xyz", [])

        assert count == 0
        mock_api.annotation_queues.create_queue_item.assert_not_called()

    def test_passes_correct_queue_id(self):
        """Queue ID is passed to each create_queue_item call."""
        module = _load_module()

        mock_api = MagicMock()
        module.add_traces_to_queue(mock_api, "queue-abc", ["trace-1"])

        call_kwargs = mock_api.annotation_queues.create_queue_item.call_args.kwargs
        assert call_kwargs["queue_id"] == "queue-abc"

    def test_uses_create_queue_item_not_create(self):
        """Must call create_queue_item, not create (wrong method)."""
        module = _load_module()

        mock_api = MagicMock()
        module.add_traces_to_queue(mock_api, "queue-xyz", ["trace-1"])

        mock_api.annotation_queues.create_queue_item.assert_called_once()


# ---------------------------------------------------------------------------
# triage_dislike_traces (main orchestration)
# ---------------------------------------------------------------------------


class TestTriageDislikeTraces:
    def test_full_flow_returns_stats(self):
        """Returns dict with trace_count and added_count."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(
            data=[
                SimpleNamespace(trace_id="t1", value=0.0),
                SimpleNamespace(trace_id="t2", value=0.0),
            ],
            meta=_make_meta(),
        )
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="q-1", name="dislike-review")], meta=_make_meta()
        )

        stats = module.triage_dislike_traces(
            mock_api,
            queue_name="dislike-review",
            hours=24,
            dry_run=False,
        )

        assert stats["trace_count"] == 2
        assert stats["added_count"] == 2

    def test_dry_run_skips_queue_operations(self):
        """In dry-run mode, no items are added to the queue."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(
            data=[SimpleNamespace(trace_id="t1", value=0.0)],
            meta=_make_meta(),
        )

        stats = module.triage_dislike_traces(
            mock_api,
            queue_name="dislike-review",
            hours=24,
            dry_run=True,
        )

        mock_api.annotation_queues.create_queue_item.assert_not_called()
        mock_api.annotation_queues.list_queues.assert_not_called()
        mock_api.annotation_queues.create_queue.assert_not_called()
        assert stats["trace_count"] == 1
        assert stats["added_count"] == 0

    def test_no_op_when_no_dislikes(self):
        """No queue operations when no dislike traces found."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(data=[], meta=_make_meta())

        stats = module.triage_dislike_traces(
            mock_api,
            queue_name="dislike-review",
            hours=24,
            dry_run=False,
        )

        mock_api.annotation_queues.list_queues.assert_not_called()
        mock_api.annotation_queues.create_queue_item.assert_not_called()
        assert stats["trace_count"] == 0
        assert stats["added_count"] == 0

    def test_uses_custom_queue_name(self):
        """Custom queue name is passed through to get_or_create_annotation_queue."""
        module = _load_module()

        mock_api = MagicMock()
        mock_api.score_v_2.get.return_value = SimpleNamespace(
            data=[SimpleNamespace(trace_id="t1", value=0.0)],
            meta=_make_meta(),
        )
        mock_api.annotation_queues.list_queues.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="q-custom", name="my-queue")], meta=_make_meta()
        )

        module.triage_dislike_traces(
            mock_api,
            queue_name="my-queue",
            hours=24,
            dry_run=False,
        )

        # Verify list_queues was called and create_queue_item received the custom queue id
        mock_api.annotation_queues.list_queues.assert_called_once()
        create_kwargs = mock_api.annotation_queues.create_queue_item.call_args.kwargs
        assert create_kwargs["queue_id"] == "q-custom"


# ---------------------------------------------------------------------------
# QUEUE_NAME constant
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_queue_name_is_dislike_review(self):
        """Default queue name must be 'dislike-review'."""
        module = _load_module()
        assert module.QUEUE_NAME == "dislike-review"

    def test_score_name_is_user_feedback(self):
        """Score name constant must be 'user_feedback'."""
        module = _load_module()
        assert module.SCORE_NAME == "user_feedback"
