#!/usr/bin/env python3
"""CLI for LLM-as-a-Judge batch evaluation on Langfuse traces.

Usage:
    uv run python scripts/evaluate_judge.py --hours 24 --tag rag
    uv run python scripts/evaluate_judge.py --hours 48 --tag chat --sample-rate 0.5
    uv run python scripts/evaluate_judge.py --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def main():
    parser = argparse.ArgumentParser(description="LLM-as-a-Judge batch evaluation")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default: 24)")
    parser.add_argument(
        "--tag", type=str, default="rag", help="Filter traces by tag (default: rag)"
    )
    parser.add_argument(
        "--sample-rate", type=float, default=1.0, help="Fraction to evaluate (default: 1.0)"
    )
    parser.add_argument("--model", type=str, default=None, help="Judge LLM model (default: env)")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    from telegram_bot.evaluation.runner import run_batch

    summary = asyncio.run(
        run_batch(
            hours=args.hours,
            tag=args.tag,
            sample_rate=args.sample_rate,
            model=args.model,
        )
    )

    print(json.dumps(summary, indent=2))

    # Exit 1 if no traces evaluated (useful for CI)
    if summary["evaluated"] == 0 and summary["total_traces"] > 0:
        print("WARNING: No traces could be evaluated (missing context data?)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
