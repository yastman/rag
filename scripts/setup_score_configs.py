#!/usr/bin/env python3
"""Score config definitions for RAG pipeline scoring (#753).

Langfuse SDK removed (#2969). This script retains SCORE_CONFIGS data and
helper functions for reference; Langfuse upload is no longer supported.
The SCORE_CONFIGS structure is still tested to document the intended schema.

Usage (no-op — Langfuse removed):
    uv run python -m scripts.setup_score_configs
"""

from __future__ import annotations

import logging
import sys
from typing import Any


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Score Config definitions
# ---------------------------------------------------------------------------

SCORE_CONFIGS: list[dict[str, Any]] = [
    {
        "name": "user_feedback",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "user_feedback_reason",
        "data_type": "CATEGORICAL",
        "categories": [
            {"label": "wrong_topic", "value": 0},
            {"label": "missing_info", "value": 1},
            {"label": "bad_sources", "value": 2},
            {"label": "hallucination", "value": 3},
            {"label": "incomplete", "value": 4},
            {"label": "formatting", "value": 5},
        ],
    },
    {
        "name": "implicit_retry",
        "data_type": "BOOLEAN",
    },
    {
        "name": "judge_faithfulness",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "judge_answer_relevance",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "judge_context_relevance",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "latency_total_ms",
        "data_type": "NUMERIC",
        "min_value": None,
        "max_value": None,
    },
    {
        "name": "confidence_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
    },
]

_DATA_TYPE_MAP = {
    "NUMERIC": "NUMERIC",
    "CATEGORICAL": "CATEGORICAL",
    "BOOLEAN": "BOOLEAN",
}


def get_existing_configs(api: Any) -> dict[str, str]:
    """Return {name: id} mapping for non-archived score configs."""
    response = api.score_configs.get()
    return {item.name: item.id for item in response.data if not item.is_archived}


def setup_score_configs(api: Any) -> dict[str, str]:
    """Create all required score configs. Skip configs that already exist.

    Args:
        api: Any object with a score_configs.get / score_configs.create interface.

    Returns:
        Mapping of {config_name: config_id} for all required configs.
    """
    existing = get_existing_configs(api)
    result: dict[str, str] = dict(existing)

    for cfg in SCORE_CONFIGS:
        name = cfg["name"]
        if name in existing:
            logger.info("Skipping existing config: %s (%s)", name, existing[name])
            continue

        data_type = _DATA_TYPE_MAP[cfg["data_type"]]

        kwargs: dict[str, Any] = {"name": name, "data_type": data_type}

        if cfg.get("min_value") is not None:
            kwargs["min_value"] = cfg["min_value"]
        if cfg.get("max_value") is not None:
            kwargs["max_value"] = cfg["max_value"]

        if cfg.get("categories"):
            kwargs["categories"] = [
                {"label": cat["label"], "value": cat["value"]} for cat in cfg["categories"]
            ]

        created = api.score_configs.create(**kwargs)
        result[name] = created.id
        logger.info("Created score config: %s (%s)", name, created.id)

    return result


def main() -> None:
    logger.error(
        "setup_score_configs: Langfuse removed (#2969). This script is a no-op. "
        "Score config definitions are preserved in SCORE_CONFIGS for reference."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
