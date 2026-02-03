# src/ingestion/unified/cli.py
"""CLI for unified ingestion pipeline."""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("cocoindex").setLevel(logging.INFO)


def cmd_run(args: argparse.Namespace) -> int:
    """Run ingestion."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import run_once, run_watch

    config = UnifiedConfig()

    if args.watch:
        logging.info("Starting CocoIndex watch mode (FlowLiveUpdater)")
        run_watch(config)
    else:
        run_once(config)

    return 0


async def cmd_status(args: argparse.Namespace) -> int:
    """Show ingestion status."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.state_manager import UnifiedStateManager

    config = UnifiedConfig()
    manager = UnifiedStateManager(database_url=config.database_url)

    try:
        stats = await manager.get_stats()
        dlq_count = await manager.get_dlq_count()

        print("\n=== Ingestion Status ===")
        total = sum(stats.values())
        for status, count in sorted(stats.items()):
            pct = count / total * 100 if total else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        print(f"  TOTAL: {total}")
        print(f"\n  DLQ: {dlq_count} items")
        print(f"  Collection: {config.collection_name}")
        print(f"  Sync dir: {config.sync_dir}")
    finally:
        await manager.close()

    return 0


async def cmd_reprocess(args: argparse.Namespace) -> int:
    """Reprocess a specific file or all errors."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.state_manager import UnifiedStateManager

    config = UnifiedConfig()
    manager = UnifiedStateManager(database_url=config.database_url)

    try:
        pool = await manager._get_pool()

        if args.file_id:
            # Reset specific file
            await pool.execute(
                "UPDATE ingestion_state SET status = 'pending', retry_count = 0, "
                "retry_after = NULL WHERE file_id = $1",
                args.file_id,
            )
            print(f"Reset file: {args.file_id}")
        elif args.errors:
            # Reset all errors
            result = await pool.execute(
                "UPDATE ingestion_state SET status = 'pending', retry_count = 0, "
                "retry_after = NULL WHERE status = 'error'"
            )
            print(f"Reset error files: {result}")
        else:
            print("Specify --file-id or --errors")
            return 1
    finally:
        await manager.close()

    return 0


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

    # status
    subparsers.add_parser("status", help="Show status")

    # reprocess
    reprocess_p = subparsers.add_parser("reprocess", help="Reprocess files")
    reprocess_p.add_argument("--file-id", help="Specific file ID")
    reprocess_p.add_argument("--errors", action="store_true", help="All error files")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "run":
        return cmd_run(args)
    if args.command == "status":
        return asyncio.run(cmd_status(args))
    if args.command == "reprocess":
        return asyncio.run(cmd_reprocess(args))

    return 1


if __name__ == "__main__":
    sys.exit(main())
