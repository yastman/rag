#!/usr/bin/env python3
"""Export low-scoring Langfuse traces into versioned evaluation datasets.

Filters production traces by judge scores (faithfulness, relevance, context),
no_results flag, and error observations. Creates Langfuse dataset items with
source trace linking and saves a local JSONL backup.

Usage:
    uv run python scripts/export_traces_to_dataset.py --days 7
    uv run python scripts/export_traces_to_dataset.py --dry-run
    uv run python scripts/export_traces_to_dataset.py --dataset-name custom-v1 --days 14
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50

# Judge score thresholds from tests/baseline/thresholds.yaml
SCORE_THRESHOLDS: dict[str, float] = {
    "judge_faithfulness": 0.75,
    "judge_answer_relevance": 0.70,
    "judge_context_relevance": 0.65,
}

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"


# ---------------------------------------------------------------------------
# Trace analysis helpers
# ---------------------------------------------------------------------------


def get_trace_scores(trace: Any) -> dict[str, float]:
    """Extract numeric scores from a Langfuse trace."""
    scores: dict[str, float] = {}
    for s in trace.scores or []:
        name = getattr(s, "name", "")
        value = getattr(s, "value", None)
        if name and isinstance(value, int | float):
            scores[name] = float(value)
    return scores


def classify_export_reasons(scores: dict[str, float]) -> list[str]:
    """Determine why a trace should be exported.

    Returns list of reason strings (empty = trace is fine, skip it).
    """
    reasons: list[str] = []
    for score_name, threshold in SCORE_THRESHOLDS.items():
        if score_name in scores and scores[score_name] < threshold:
            reasons.append(f"low_{score_name}")
    if scores.get("no_results", 0) >= 1.0:
        reasons.append("no_results")
    return reasons


def extract_item_data(
    trace: Any,
    observations: list[Any],
) -> dict[str, Any] | None:
    """Extract query/answer/context from a trace for dataset item creation.

    Returns None if essential data (query) is missing.
    """
    query = ""
    if isinstance(trace.input, dict):
        query = trace.input.get("query", "")
    if not query:
        return None

    answer = ""
    if isinstance(trace.output, dict):
        answer = trace.output.get("response", "")
    if not answer:
        return None

    # Extract retrieved context from node-retrieve observation
    context_parts: list[str] = []
    for obs in observations:
        if getattr(obs, "name", "") != "node-retrieve":
            continue
        output = getattr(obs, "output", None)
        if not isinstance(output, dict):
            continue
        for doc in output.get("retrieved_context", []):
            if isinstance(doc, dict) and doc.get("content"):
                context_parts.append(str(doc["content"]))

    return {
        "query": query,
        "answer": answer,
        "context": context_parts,
    }


# ---------------------------------------------------------------------------
# Langfuse trace fetching
# ---------------------------------------------------------------------------


def fetch_exportable_traces(
    langfuse: Any,
    *,
    days: int = 7,
    tag: str = "rag",
) -> list[dict[str, Any]]:
    """Fetch traces with low scores from Langfuse API.

    Returns list of dicts ready for dataset item creation.
    """
    from_ts = datetime.now(UTC) - timedelta(days=days)
    page = 1
    total_scanned = 0
    items: list[dict[str, Any]] = []

    while True:
        traces_resp = langfuse.api.trace.list(
            page=page,
            limit=BATCH_SIZE,
            tags=tag,
            from_timestamp=from_ts,
        )
        traces = traces_resp.data
        if not traces:
            break

        for trace in traces:
            total_scanned += 1
            scores = get_trace_scores(trace)

            # Skip traces without judge scores (not yet evaluated)
            has_judge = any(s in scores for s in SCORE_THRESHOLDS)
            if not has_judge:
                continue

            reasons = classify_export_reasons(scores)
            if not reasons:
                continue

            # Fetch observations for context extraction
            obs_page = langfuse.api.observations.get_many(
                trace_id=trace.id,
                type="SPAN",
                page=1,
                limit=50,
            )
            observations = obs_page.data or []

            data = extract_item_data(trace, observations)
            if data is None:
                logger.debug("Skipping trace %s: no query/answer data", trace.id)
                continue

            items.append(
                {
                    "trace_id": trace.id,
                    "query": data["query"],
                    "answer": data["answer"],
                    "context": data["context"],
                    "scores": scores,
                    "reasons": reasons,
                }
            )

        page += 1

    logger.info(
        "Scanned %d traces, found %d exportable (days=%d, tag=%s)",
        total_scanned,
        len(items),
        days,
        tag,
    )
    return items


# ---------------------------------------------------------------------------
# Export to Langfuse dataset
# ---------------------------------------------------------------------------


def export_to_langfuse(
    langfuse: Any,
    dataset_name: str,
    items: list[dict[str, Any]],
) -> int:
    """Create Langfuse dataset and populate with items.

    Returns count of items created.
    """
    langfuse.create_dataset(name=dataset_name)
    created = 0

    for item in items:
        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            input={"query": item["query"]},
            expected_output={"response": item["answer"]},
            source_trace_id=item["trace_id"],
            metadata={
                "scores": item["scores"],
                "reasons": item["reasons"],
                "context": item["context"],
                "context_count": len(item["context"]),
                "exported_at": datetime.now(UTC).isoformat(),
            },
        )
        created += 1

    langfuse.flush()
    logger.info("Created %d items in Langfuse dataset '%s'", created, dataset_name)
    return created


# ---------------------------------------------------------------------------
# Export to local JSONL
# ---------------------------------------------------------------------------


def export_to_jsonl(
    output_path: Path,
    items: list[dict[str, Any]],
) -> None:
    """Export items to a local JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for item in items:
            record = {
                "input": {"query": item["query"]},
                "expected_output": {"response": item["answer"]},
                "metadata": {
                    "source_trace_id": item["trace_id"],
                    "scores": item["scores"],
                    "reasons": item["reasons"],
                    "context": item["context"],
                    "context_count": len(item["context"]),
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Exported %d items to %s", len(items), output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def make_dataset_name(prefix: str = "rag-eval") -> str:
    """Generate versioned dataset name: rag-eval-YYYYMMDD."""
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%d')}"


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Export low-scoring Langfuse traces to evaluation datasets",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Look back N days for traces (default: 7)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="rag",
        help="Filter traces by tag (default: rag)",
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default=None,
        help="Langfuse dataset name (default: rag-eval-YYYYMMDD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without creating anything",
    )
    parser.add_argument(
        "--skip-langfuse-upload",
        action="store_true",
        help="Export to local JSONL only, skip Langfuse dataset creation",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DATASETS_DIR),
        help="Directory for local JSONL export (default: datasets/)",
    )
    args = parser.parse_args()

    from langfuse import Langfuse

    langfuse = Langfuse()
    if not langfuse.auth_check():
        logger.error("Langfuse auth check failed — check credentials")
        sys.exit(1)

    dataset_name = args.dataset_name or make_dataset_name()
    items = fetch_exportable_traces(langfuse, days=args.days, tag=args.tag)

    if not items:
        logger.info("No exportable traces found. Nothing to do.")
        return

    # Summary table
    logger.info("--- Export Summary ---")
    reason_counts: dict[str, int] = {}
    for item in items:
        for r in item["reasons"]:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    for reason, count in sorted(reason_counts.items()):
        logger.info("  %s: %d traces", reason, count)

    if args.dry_run:
        logger.info("DRY RUN — would export %d items to '%s'", len(items), dataset_name)
        for item in items[:5]:
            logger.info(
                "  trace=%s reasons=%s query=%s",
                item["trace_id"][:12],
                item["reasons"],
                item["query"][:60],
            )
        if len(items) > 5:
            logger.info("  ... and %d more", len(items) - 5)
        return

    # Export to local JSONL
    output_dir = Path(args.output_dir)
    jsonl_path = output_dir / f"{dataset_name}.jsonl"
    export_to_jsonl(jsonl_path, items)

    # Export to Langfuse dataset
    if not args.skip_langfuse_upload:
        export_to_langfuse(langfuse, dataset_name, items)

    logger.info("Done: %d items → dataset '%s'", len(items), dataset_name)


if __name__ == "__main__":
    main()
