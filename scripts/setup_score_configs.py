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

from src.observability import Langfuse, get_score_config_types


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

_DATA_TYPE_MAP: dict[str, Any] | None = None


def _get_data_type_map() -> dict[str, Any]:
    """Lazily build the data type map using Langfuse SDK types."""
    global _DATA_TYPE_MAP
    if _DATA_TYPE_MAP is not None:
        return _DATA_TYPE_MAP
    types = get_score_config_types()
    if types is None:
        raise RuntimeError("Langfuse SDK not available — cannot build score config type map")
    _, ScoreConfigDataType = types
    _DATA_TYPE_MAP = {
        "NUMERIC": ScoreConfigDataType.NUMERIC,
        "CATEGORICAL": ScoreConfigDataType.CATEGORICAL,
        "BOOLEAN": ScoreConfigDataType.BOOLEAN,
    }
    return _DATA_TYPE_MAP


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

    data_type_map = _get_data_type_map()
    score_config_types = get_score_config_types()
    ConfigCategory = score_config_types[0] if score_config_types else None

    for cfg in SCORE_CONFIGS:
        name = cfg["name"]
        if name in existing:
            logger.info("Skipping existing config: %s (%s)", name, existing[name])
            continue

        data_type = data_type_map[cfg["data_type"]]

        kwargs: dict[str, Any] = {"name": name, "data_type": data_type}

        if cfg.get("min_value") is not None:
            kwargs["min_value"] = cfg["min_value"]
        if cfg.get("max_value") is not None:
            kwargs["max_value"] = cfg["max_value"]

        if cfg.get("categories"):
            if ConfigCategory is None:
                raise RuntimeError("Langfuse ConfigCategory type unavailable")
            kwargs["categories"] = [
                ConfigCategory(label=cat["label"], value=cat["value"]) for cat in cfg["categories"]
            ]

        created = api.score_configs.create(**kwargs)
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
