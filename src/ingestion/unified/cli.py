# src/ingestion/unified/cli.py
"""CLI for unified ingestion pipeline."""

import argparse
import asyncio
import logging
import os
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


async def cmd_preflight(args: argparse.Namespace) -> int:
    """Check that all ingestion dependencies are reachable."""
    import httpx

    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    timeout = httpx.Timeout(float(os.getenv("BGE_M3_TIMEOUT", "60")))
    results: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Qdrant reachable + collection exists
        try:
            resp = await client.get(f"{config.qdrant_url}/collections/{config.collection_name}")
            results["qdrant"] = resp.status_code == 200
            if results["qdrant"]:
                data = resp.json().get("result", {})
                points = data.get("points_count", "?")
                print(f"  [OK] Qdrant collection '{config.collection_name}' ({points} points)")
            else:
                print(
                    f"  [FAIL] Qdrant collection '{config.collection_name}' — HTTP {resp.status_code}"
                )
        except Exception as e:
            results["qdrant"] = False
            print(f"  [FAIL] Qdrant ({config.qdrant_url}) — {e}")

        # BGE-M3 dense endpoint
        try:
            resp = await client.post(
                f"{config.bge_m3_url}/encode/dense",
                json={"texts": ["ping"]},
            )
            results["bge_m3_dense"] = resp.status_code == 200
            if results["bge_m3_dense"]:
                print(f"  [OK] BGE-M3 dense ({config.bge_m3_url}/encode/dense)")
            else:
                print(f"  [FAIL] BGE-M3 dense — HTTP {resp.status_code}")
        except Exception as e:
            results["bge_m3_dense"] = False
            print(f"  [FAIL] BGE-M3 dense ({config.bge_m3_url}) — {e}")

        # BGE-M3 sparse endpoint
        try:
            resp = await client.post(
                f"{config.bge_m3_url}/encode/sparse",
                json={"texts": ["ping"]},
            )
            results["bge_m3_sparse"] = resp.status_code == 200
            if results["bge_m3_sparse"]:
                print(f"  [OK] BGE-M3 sparse ({config.bge_m3_url}/encode/sparse)")
            else:
                print(f"  [FAIL] BGE-M3 sparse — HTTP {resp.status_code}")
        except Exception as e:
            results["bge_m3_sparse"] = False
            print(f"  [FAIL] BGE-M3 sparse ({config.bge_m3_url}) — {e}")

        # Docling service
        try:
            resp = await client.get(f"{config.docling_url}/health")
            results["docling"] = resp.status_code == 200
            if results["docling"]:
                print(f"  [OK] Docling ({config.docling_url})")
            else:
                print(f"  [FAIL] Docling — HTTP {resp.status_code}")
        except Exception as e:
            results["docling"] = False
            print(f"  [FAIL] Docling ({config.docling_url}) — {e}")

    # Required env vars
    required_vars = ["QDRANT_URL", "BGE_M3_URL", "DOCLING_URL", "INGESTION_DATABASE_URL"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        results["env_vars"] = False
        print(f"  [WARN] Missing env vars: {', '.join(missing)} (using defaults)")
    else:
        results["env_vars"] = True
        print("  [OK] All required env vars set")

    # Summary
    ok = sum(1 for v in results.values() if v)
    total = len(results)
    all_ok = ok == total
    print(f"\nPreflight: {ok}/{total} checks passed {'— READY' if all_ok else '— NOT READY'}")
    return 0 if all_ok else 1


async def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Create Qdrant collection if it doesn't exist."""
    from qdrant_client import QdrantClient
    from qdrant_client.http.exceptions import UnexpectedResponse
    from qdrant_client.models import (
        BinaryQuantization,
        BinaryQuantizationConfig,
        Distance,
        HnswConfigDiff,
        Modifier,
        MultiVectorComparator,
        MultiVectorConfig,
        OptimizersConfigDiff,
        SparseVectorParams,
        VectorParams,
    )

    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    collection_name = config.collection_name
    dense_dimension = 1024

    print(f"\n=== Bootstrap: {collection_name} ===")

    client = QdrantClient(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=60,
    )

    # Check connection
    try:
        client.get_collections()
    except Exception as e:
        print(f"  [FAIL] Cannot connect to Qdrant: {e}")
        return 1

    # Check if collection already exists
    exists = False
    try:
        client.get_collection(collection_name)
        exists = True
    except (UnexpectedResponse, Exception):
        pass

    if exists:
        print(f"  Collection '{collection_name}' already exists — nothing to do.")
        return 0

    # Create collection
    print(f"  Creating collection: {collection_name}")
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": VectorParams(
                size=dense_dimension,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200, on_disk=False),
                quantization_config=BinaryQuantization(
                    binary=BinaryQuantizationConfig(always_ram=True)
                ),
                on_disk=True,
            ),
            "colbert": VectorParams(
                size=dense_dimension,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                hnsw_config=HnswConfigDiff(m=0),
                on_disk=True,
            ),
        },
        sparse_vectors_config={
            "bm42": SparseVectorParams(modifier=Modifier.IDF),
        },
        optimizers_config=OptimizersConfigDiff(
            indexing_threshold=20000,
            memmap_threshold=50000,
        ),
    )

    # Create payload indexes
    print("  Creating payload indexes...")
    for field in [
        "file_id",
        "metadata.file_id",
        "metadata.doc_id",
        "metadata.source",
        "metadata.file_name",
        "metadata.mime_type",
    ]:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema="keyword",
            )
        except Exception as e:
            print(f"  Warning: Could not create index {field}: {e}")

    for field in ["metadata.order", "metadata.chunk_id"]:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema="integer",
            )
        except Exception as e:
            print(f"  Warning: Could not create index {field}: {e}")

    print(f"  Bootstrap completed: {collection_name}")
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

    # preflight
    subparsers.add_parser("preflight", help="Check dependencies are reachable")

    # bootstrap
    subparsers.add_parser("bootstrap", help="Create Qdrant collection if missing")

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
    if args.command == "preflight":
        return asyncio.run(cmd_preflight(args))
    if args.command == "bootstrap":
        return asyncio.run(cmd_bootstrap(args))
    if args.command == "reprocess":
        return asyncio.run(cmd_reprocess(args))

    return 1


if __name__ == "__main__":
    sys.exit(main())
