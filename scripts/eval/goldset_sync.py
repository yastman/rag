#!/usr/bin/env python3
"""Sync ground truth JSON to Langfuse dataset for experiments.

Usage:
    uv run python scripts/eval/goldset_sync.py
    uv run python scripts/eval/goldset_sync.py --dataset-name rag-gold-set-v2
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

DEFAULT_GROUND_TRUTH = "tests/eval/ground_truth.json"
DEFAULT_DATASET_NAME = "rag-gold-set"


def load_ground_truth(path: str) -> list[dict[str, Any]]:
    """Load ground truth samples from JSON file."""
    data = json.loads(Path(path).read_text())
    return data["samples"]


def sync_to_langfuse(
    langfuse: Any,
    dataset_name: str,
    samples: list[dict[str, Any]],
) -> int:
    """Sync samples to Langfuse dataset. Creates dataset if not exists.

    Returns number of items created.
    """
    try:
        dataset = langfuse.get_dataset(dataset_name)
        logger.info("Found existing dataset: %s", dataset_name)
    except Exception:
        dataset = langfuse.create_dataset(name=dataset_name)
        logger.info("Created new dataset: %s", dataset_name)

    created = 0
    for sample in samples:
        item_id = f"{dataset_name}-{sample.get('id', created)}"
        dataset.create_item(
            id=item_id,
            input={"question": sample["question"]},
            expected_output={"answer": sample["ground_truth"]},
            metadata={
                "id": sample.get("id"),
                "category": sample.get("category", ""),
                "difficulty": sample.get("difficulty", ""),
                "expected_topics": sample.get("expected_topics", []),
            },
        )
        created += 1

    langfuse.flush()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync gold set to Langfuse dataset")
    parser.add_argument(
        "--ground-truth", default=DEFAULT_GROUND_TRUTH, help="Path to ground truth JSON"
    )
    parser.add_argument(
        "--dataset-name", default=DEFAULT_DATASET_NAME, help="Langfuse dataset name"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from langfuse import Langfuse

    langfuse = Langfuse()
    samples = load_ground_truth(args.ground_truth)
    count = sync_to_langfuse(langfuse, args.dataset_name, samples)
    print(f"Synced {count} items to dataset '{args.dataset_name}'")


if __name__ == "__main__":
    main()
