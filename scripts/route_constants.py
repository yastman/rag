#!/usr/bin/env python3
"""Canonical Kiro worker route models for tmux swarm helpers."""

from __future__ import annotations

import argparse


DEFAULT_WORKER_MODEL = "claude-sonnet-4.6"
DEFAULT_SECRETARY_FLASH_MODEL = "claude-haiku-4.5"

CANONICAL_WORKER_ROUTES = {
    "implementation": ("kiro-worker", DEFAULT_WORKER_MODEL),
    "plan-execution": ("kiro-worker", DEFAULT_WORKER_MODEL),
    "quick": ("kiro-worker", DEFAULT_WORKER_MODEL),
    "local-verification": ("kiro-worker", DEFAULT_WORKER_MODEL),
    "pr-review": ("kiro-worker-opus", DEFAULT_WORKER_MODEL),
    "review-fix": ("kiro-worker", DEFAULT_WORKER_MODEL),
}

SECRETARY_AGENT_MODELS = {
    "secretary-flash": DEFAULT_SECRETARY_FLASH_MODEL,
    "secretary-pro": DEFAULT_WORKER_MODEL,
}

RECOMMENDED_ROUTE_MODELS = {
    "secretary-pro": DEFAULT_WORKER_MODEL,
    "implementation": DEFAULT_WORKER_MODEL,
    "pr-review": DEFAULT_WORKER_MODEL,
    "review-fix": DEFAULT_WORKER_MODEL,
    "local-verification": DEFAULT_WORKER_MODEL,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "field",
        choices=("default-worker-model", "default-secretary-flash-model"),
    )
    args = parser.parse_args()
    if args.field == "default-worker-model":
        print(DEFAULT_WORKER_MODEL)
    else:
        print(DEFAULT_SECRETARY_FLASH_MODEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
