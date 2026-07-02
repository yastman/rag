# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""CLI entry point and dispatcher for the unified ingestion pipeline."""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

from src.ingestion.unified.commands import (
    _inspect_sync_dir,  # noqa: F401 — re-exported for backward compat
    cmd_backfill_colbert,
    cmd_bootstrap,
    cmd_coverage_check,
    cmd_preflight,
    cmd_run,
    cmd_schema_check,
)
from src.ingestion.unified.observability import flush_ingestion_traces


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> int:
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Unified Ingestion Pipeline (v3.2.1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = subparsers.add_parser("run", help="Run ingestion")
    run_p.add_argument("--watch", "-w", action="store_true", help="Continuous mode")

    # preflight
    subparsers.add_parser("preflight", help="Check dependencies are reachable")

    # bootstrap
    bootstrap_p = subparsers.add_parser("bootstrap", help="Create Qdrant collection if missing")
    bootstrap_p.add_argument(
        "--require-colbert",
        action="store_true",
        help="Fail if existing/new collection schema misses 'colbert' vector",
    )

    # schema-check
    schema_check_p = subparsers.add_parser(
        "schema-check",
        help="Validate collection schema (dense/bm42 and optional colbert)",
    )
    schema_check_p.add_argument(
        "--require-colbert",
        action="store_true",
        help="Require 'colbert' vector to be present",
    )
    # coverage-check
    coverage_check_p = subparsers.add_parser(
        "coverage-check",
        help="Check point-level ColBERT vector coverage",
    )
    coverage_check_p.add_argument(
        "--min-ratio",
        type=float,
        default=0.995,
        help="Minimum acceptable ColBERT coverage ratio (default: 0.995)",
    )

    # backfill-colbert
    backfill_p = subparsers.add_parser(
        "backfill-colbert",
        help="Backfill missing ColBERT vectors for existing points",
    )
    backfill_p.add_argument("--batch-size", type=int, default=32, help="Batch size")
    backfill_p.add_argument("--limit", type=int, help="Process at most N points")
    backfill_p.add_argument("--dry-run", action="store_true", help="Do not write updates")
    backfill_p.add_argument("--resume", action="store_true", help="Resume from checkpoint")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # #2214: ensure buffered ingestion traces are flushed even if a command
    # raises or exits abruptly (the BatchSpanProcessor only auto-flushes on a
    # clean atexit). flush_ingestion_traces() is a no-op when tracing is off.
    try:
        if args.command == "run":
            return cmd_run(args)  # type: ignore[no-any-return]
        if args.command == "preflight":
            return asyncio.run(cmd_preflight(args))  # type: ignore[no-any-return]
        if args.command == "bootstrap":
            return asyncio.run(cmd_bootstrap(args))  # type: ignore[no-any-return]
        if args.command == "schema-check":
            return asyncio.run(cmd_schema_check(args))  # type: ignore[no-any-return]
        if args.command == "coverage-check":
            return asyncio.run(cmd_coverage_check(args))  # type: ignore[no-any-return]
        if args.command == "backfill-colbert":
            return cmd_backfill_colbert(args)

        return 1
    finally:
        flush_ingestion_traces()


if __name__ == "__main__":
    sys.exit(main())
