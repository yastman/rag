#!/usr/bin/env python3
"""Setup Langfuse Score Configs for typed scoring (#753).

Creates Score Configs in Langfuse for structured, typed scoring of RAG pipeline traces.
Idempotent: checks existing configs before creating new ones.

Usage:
    uv run python -m scripts.setup_score_configs
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.api.resources.commons.types.config_category import ConfigCategory
from langfuse.api.resources.commons.types.score_config_data_type import ScoreConfigDataType
from langfuse.api.resources.score_configs.types.create_score_config_request import (
    CreateScoreConfigRequest,
)


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
            {"label": "irrelevant", "value": 0},
            {"label": "incomplete", "value": 1},
            {"label": "incorrect", "value": 2},
            {"label": "too_long", "value": 3},
            {"label": "too_short", "value": 4},
            {"label": "other", "value": 5},
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
    "NUMERIC": ScoreConfigDataType.NUMERIC,
    "CATEGORICAL": ScoreConfigDataType.CATEGORICAL,
    "BOOLEAN": ScoreConfigDataType.BOOLEAN,
}


def get_existing_configs(api: Any) -> dict[str, str]:
    """Return {name: id} mapping for non-archived score configs."""
    response = api.score_configs.get()
    return {item.name: item.id for item in response.data if not item.is_archived}


def setup_score_configs(api: Any) -> dict[str, str]:
    """Create all required score configs. Skip configs that already exist.

    Args:
        api: Langfuse low-level API client (langfuse.api).

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
                ConfigCategory(label=cat["label"], value=cat["value"]) for cat in cfg["categories"]
            ]

        created = api.score_configs.create(request=CreateScoreConfigRequest(**kwargs))
        result[name] = created.id
        logger.info("Created score config: %s (%s)", name, created.id)

    return result


def main() -> None:
    load_dotenv()

    try:
        lf = Langfuse()
    except Exception as e:
        logger.error("Failed to initialize Langfuse client: %s", e)
        sys.exit(1)

    logger.info("Setting up Langfuse Score Configs...")
    result = setup_score_configs(lf.api)

    logger.info("Done. %d score config(s) ready:", len(result))
    for name, config_id in sorted(result.items()):
        logger.info("  %s → %s", name, config_id)

    lf.flush()


if __name__ == "__main__":
    main()
