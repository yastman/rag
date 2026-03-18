#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_cases() -> list[dict[str, str]]:
    fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "retrieval" / "legal_grounding_cases.yaml"
    data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def main() -> int:
    from src.retrieval.topic_classifier import get_query_topic_hint
    from telegram_bot.services.grounding_policy import (
        get_grounding_mode,
        should_safe_fallback,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    cases = _load_cases()
    if args.limit > 0:
        cases = cases[: args.limit]

    for case in cases:
        query = case["query"]
        topic_hint = get_query_topic_hint(query)
        topic_value = topic_hint.value if topic_hint is not None else None
        grounding_mode = get_grounding_mode(query_type="FAQ", topic_hint=topic_value)
        safe_fallback_used = should_safe_fallback(
            grounding_mode=grounding_mode,
            documents=[],
            sources_enabled=False,
        )
        print(
            json.dumps(
                {
                    "query": query,
                    "topic_hint": topic_value,
                    "initial_results_count": 0,
                    "results_count": 0,
                    "safe_fallback_used": safe_fallback_used,
                    "grounding_mode": grounding_mode,
                    "audit_mode": "offline_fixture_only",
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
