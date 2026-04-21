#!/usr/bin/env python3
"""Auto-triage dislike traces into Langfuse Annotation Queue (Issue #757).

Fetches traces with user_feedback=0 score from the last 24 hours and adds
each trace to the "dislike-review" Annotation Queue for manual review.

Usage:
    uv run python scripts/langfuse_triage.py
    uv run python scripts/langfuse_triage.py --dry-run
    uv run python scripts/langfuse_triage.py --hours 48 --queue my-queue
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QUEUE_NAME = "dislike-review"
SCORE_NAME = "user_feedback"
BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Scores fetching
# ---------------------------------------------------------------------------


def fetch_dislike_trace_ids(api: Any, *, hours: int = 24) -> list[str]:
    """Fetch unique trace IDs with user_feedback=0 from the last N hours.

    Uses paginated Scores API v2 to retrieve all pages.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        hours: Look-back window in hours.

    Returns:
        Deduplicated list of trace IDs.
    """
    from_ts = datetime.now(UTC) - timedelta(hours=hours)

    page = 1
    seen: set[str] = set()
    trace_ids: list[str] = []

    while True:
        response = api.score_v_2.get(
            name=SCORE_NAME,
            value=0,
            from_timestamp=from_ts,
            page=page,
            limit=BATCH_SIZE,
        )
        scores = response.data or []
        if not scores:
            break

        for score in scores:
            tid = score.trace_id
            if tid and tid not in seen:
                seen.add(tid)
                trace_ids.append(tid)

        meta = response.meta
        if meta is None or page >= meta.total_pages:
            break
        page += 1

    logger.info(
        "Found %d dislike trace(s) in last %dh (score=%s, value=0)",
        len(trace_ids),
        hours,
        SCORE_NAME,
    )
    return trace_ids


# ---------------------------------------------------------------------------
# Annotation Queue management
# ---------------------------------------------------------------------------


def get_or_create_annotation_queue(api: Any, queue_name: str) -> str:
    """Get existing annotation queue or create it.

    Uses paginated list to search across all existing queues.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        queue_name: Name of the annotation queue.

    Returns:
        Queue ID string.
    """
    page = 1
    while True:
        response = api.annotation_queues.list_queues(page=page, limit=BATCH_SIZE)
        for queue in response.data or []:
            if queue.name == queue_name:
                logger.info("Using existing annotation queue '%s' (id=%s)", queue_name, queue.id)
                return queue.id

        meta = response.meta
        if meta is None or page >= meta.total_pages:
            break
        page += 1

    created = api.annotation_queues.create_queue(name=queue_name, score_config_ids=[])
    logger.info("Created annotation queue '%s' (id=%s)", queue_name, created.id)
    return created.id


def add_traces_to_queue(api: Any, queue_id: str, trace_ids: list[str]) -> int:
    """Add trace IDs to an annotation queue as PENDING TRACE items.

    Uses objectType=TRACE (not SESSION — known Langfuse bug #9571).

    Args:
        api: Langfuse low-level API client (langfuse.api).
        queue_id: Target annotation queue ID.
        trace_ids: Trace IDs to add.

    Returns:
        Number of items added.
    """
    from langfuse.api.annotation_queues.types.annotation_queue_object_type import (
        AnnotationQueueObjectType,
    )
    from langfuse.api.annotation_queues.types.annotation_queue_status import (
        AnnotationQueueStatus,
    )

    if not trace_ids:
        return 0

    added = 0
    for trace_id in trace_ids:
        api.annotation_queues.create_queue_item(
            queue_id=queue_id,
            object_id=trace_id,
            object_type=AnnotationQueueObjectType.TRACE,
            status=AnnotationQueueStatus.PENDING,
        )
        added += 1

    logger.info("Added %d trace(s) to annotation queue (id=%s)", added, queue_id)
    return added


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def triage_dislike_traces(
    api: Any,
    *,
    queue_name: str = QUEUE_NAME,
    hours: int = 24,
    dry_run: bool = False,
) -> dict[str, int]:
    """Fetch dislike traces and add them to the annotation queue.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        queue_name: Annotation queue name.
        hours: Look-back window in hours.
        dry_run: If True, only log what would happen — no writes.

    Returns:
        Dict with 'trace_count' and 'added_count'.
    """
    trace_ids = fetch_dislike_trace_ids(api, hours=hours)

    if not trace_ids:
        logger.info("No dislike traces found — nothing to triage.")
        return {"trace_count": 0, "added_count": 0}

    if dry_run:
        logger.info("DRY RUN — would add %d trace(s) to queue '%s':", len(trace_ids), queue_name)
        for tid in trace_ids[:10]:
            logger.info("  %s", tid)
        if len(trace_ids) > 10:
            logger.info("  ... and %d more", len(trace_ids) - 10)
        return {"trace_count": len(trace_ids), "added_count": 0}

    queue_id = get_or_create_annotation_queue(api, queue_name)
    added = add_traces_to_queue(api, queue_id, trace_ids)

    return {"trace_count": len(trace_ids), "added_count": added}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Auto-triage dislike traces into Langfuse Annotation Queue",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Look-back window in hours (default: 24)",
    )
    parser.add_argument(
        "--queue",
        type=str,
        default=QUEUE_NAME,
        help=f"Annotation queue name (default: {QUEUE_NAME})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be triaged without making any changes",
    )
    args = parser.parse_args()

    from langfuse import Langfuse

    lf = Langfuse()
    if not lf.auth_check():
        logger.error("Langfuse auth check failed — check credentials")
        sys.exit(1)

    try:
        stats = triage_dislike_traces(
            lf.api,
            queue_name=args.queue,
            hours=args.hours,
            dry_run=args.dry_run,
        )
    except Exception as e:
        logger.error("Triage failed: %s", e)
        lf.flush()
        sys.exit(1)

    logger.info(
        "Done: %d dislike trace(s) found, %d added to queue '%s'",
        stats["trace_count"],
        stats["added_count"],
        args.queue,
    )
    lf.flush()


if __name__ == "__main__":
    main()
