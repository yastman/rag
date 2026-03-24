# src/ingestion/unified/cli.py
"""CLI for unified ingestion pipeline."""

import argparse
import asyncio
import logging
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.unified.colbert_backfill import (
    ColbertBackfillRunner,
    compute_colbert_coverage,
    inspect_collection_schema,
)
from src.ingestion.unified.observability import observe, try_update_ingestion_trace


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


def _inspect_sync_dir(
    sync_dir: Path, supported_extensions: frozenset[str]
) -> dict[str, int | bool]:
    """Inspect ingestion source directory health."""
    exists = sync_dir.exists()
    is_dir = sync_dir.is_dir()
    supported_files = 0

    if exists and is_dir:
        supported_files = sum(
            1
            for path in sync_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in supported_extensions
        )

    return {
        "exists": exists,
        "is_dir": is_dir,
        "supported_files": supported_files,
    }


@observe(name="ingestion-cli-run", capture_input=False, capture_output=False)
def cmd_run(args: argparse.Namespace) -> int:
    """Run ingestion."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import run_once, run_watch

    config = UnifiedConfig()
    watch_mode = bool(args.watch)
    try_update_ingestion_trace(command="run", status="started", metadata={"watch": watch_mode})

    try:
        if watch_mode:
            logging.info("Starting CocoIndex watch mode (FlowLiveUpdater)")
            run_watch(config)
        else:
            run_once(config)
    except Exception as exc:
        try_update_ingestion_trace(
            command="run",
            status="error",
            metadata={"watch": watch_mode, "error_type": type(exc).__name__},
        )
        raise

    try_update_ingestion_trace(command="run", status="completed", metadata={"watch": watch_mode})

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
        sync_info = _inspect_sync_dir(config.sync_dir, config.supported_extensions)

        print("\n=== Ingestion Status ===")
        total = sum(stats.values())
        for status, count in sorted(stats.items()):
            pct = count / total * 100 if total else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        print(f"  TOTAL: {total}")
        print(f"\n  DLQ: {dlq_count} items")
        print(f"  Collection: {config.collection_name}")
        print(f"  Sync dir: {config.sync_dir}")
        if sync_info["exists"] and sync_info["is_dir"]:
            print(f"  Supported files: {sync_info['supported_files']}")
        elif not sync_info["exists"]:
            print("  Supported files: n/a (sync dir missing)")
        else:
            print("  Supported files: n/a (sync dir is not a directory)")
    finally:
        await manager.close()

    return 0


@observe(name="ingestion-cli-preflight", capture_input=False, capture_output=False)
async def cmd_preflight(args: argparse.Namespace) -> int:
    """Check that all ingestion dependencies are reachable."""
    import httpx

    from src.ingestion.docling_native import NativeDoclingAdapter
    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    try_update_ingestion_trace(command="preflight", status="started")
    timeout = httpx.Timeout(float(os.getenv("BGE_M3_TIMEOUT", "60")))
    results: dict[str, bool] = {}
    sync_info = _inspect_sync_dir(config.sync_dir, config.supported_extensions)

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

        # Docling backend
        if config.docling_backend == "docling_native":
            try:
                NativeDoclingAdapter(max_tokens=config.max_tokens_per_chunk)._get_converter()
                results["docling"] = True
                print("  [OK] Docling native backend available")
            except Exception as e:
                results["docling"] = False
                print(f"  [FAIL] Docling native backend — {e}")
        else:
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
    required_vars = ["QDRANT_URL", "BGE_M3_URL", "INGESTION_DATABASE_URL"]
    if config.docling_backend != "docling_native":
        required_vars.append("DOCLING_URL")
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        results["env_vars"] = False
        print(f"  [WARN] Missing env vars: {', '.join(missing)} (using defaults)")
    else:
        results["env_vars"] = True
        print("  [OK] All required env vars set")

    if not sync_info["exists"]:
        results["sync_dir"] = False
        print(f"  [FAIL] Sync dir missing: {config.sync_dir}")
    elif not sync_info["is_dir"]:
        results["sync_dir"] = False
        print(f"  [FAIL] Sync dir is not a directory: {config.sync_dir}")
    else:
        results["sync_dir"] = True
        print(
            f"  [OK] Sync dir: {config.sync_dir} ({sync_info['supported_files']} supported files)"
        )

    # Summary
    ok = sum(1 for v in results.values() if v)
    total = len(results)
    all_ok = ok == total
    print(f"\nPreflight: {ok}/{total} checks passed {'— READY' if all_ok else '— NOT READY'}")
    try_update_ingestion_trace(
        command="preflight",
        status="completed" if all_ok else "failed",
        metadata={"checks_passed": ok, "checks_total": total},
    )
    return 0 if all_ok else 1


def _extract_vector_names(collection_info) -> tuple[set[str], set[str]]:
    """Extract named dense/sparse vector names from a Qdrant collection."""
    params = getattr(getattr(collection_info, "config", None), "params", None)
    vectors = getattr(params, "vectors", {})
    sparse_vectors = getattr(params, "sparse_vectors", {})

    dense_names: set[str] = set()
    sparse_names: set[str] = set()

    if isinstance(vectors, Mapping) or hasattr(vectors, "keys"):
        dense_names = set(vectors.keys())

    if isinstance(sparse_vectors, Mapping) or hasattr(sparse_vectors, "keys"):
        sparse_names = set(sparse_vectors.keys())

    return dense_names, sparse_names


def _schema_requirements_status(
    collection_info,
    *,
    require_colbert: bool,
) -> tuple[list[str], set[str], set[str]]:
    """Validate required vector names and return missing requirements."""
    dense_names, sparse_names = _extract_vector_names(collection_info)
    missing: list[str] = []

    if "dense" not in dense_names:
        missing.append("dense")
    if "bm42" not in sparse_names:
        missing.append("bm42")
    if require_colbert and "colbert" not in dense_names:
        missing.append("colbert")

    return missing, dense_names, sparse_names


async def cmd_schema_check(args: argparse.Namespace) -> int:
    """Validate Qdrant collection schema for required vector names."""
    from qdrant_client import QdrantClient
    from qdrant_client.http.exceptions import UnexpectedResponse

    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    collection_name = config.collection_name

    print(f"\n=== Schema Check: {collection_name} ===")

    client = QdrantClient(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=60,
    )

    try:
        schema = inspect_collection_schema(client, collection_name)
    except UnexpectedResponse as exc:
        print(f"  [FAIL] Cannot load collection '{collection_name}': {exc}")
        return 1
    except Exception as exc:
        print(f"  [FAIL] Qdrant error while loading '{collection_name}': {exc}")
        return 1

    dense_names = schema["dense_names"]
    sparse_names = schema["sparse_names"]
    missing = sorted(schema["missing_dense"] | schema["missing_sparse"])
    if getattr(args, "require_colbert", False):
        missing.extend(sorted(schema["missing_colbert"]))
    if missing:
        print(
            "  [FAIL] Schema drift detected: missing "
            f"{', '.join(sorted(missing))}. "
            f"dense={sorted(dense_names)} sparse={sorted(sparse_names)}"
        )
        return 1

    print(f"  [OK] Schema valid: dense={sorted(dense_names)} sparse={sorted(sparse_names)}")
    return 0


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
        PayloadSchemaType,
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
    existing_info = None
    try:
        existing_info = client.get_collection(collection_name)
        exists = True
    except (UnexpectedResponse, Exception):
        pass

    if exists:
        print(f"  Collection '{collection_name}' already exists.")
        if getattr(args, "require_colbert", False):
            missing, dense_names, sparse_names = _schema_requirements_status(
                existing_info,
                require_colbert=True,
            )
            if missing:
                print(
                    "  [FAIL] Existing collection schema drift: missing "
                    f"{', '.join(sorted(missing))}. "
                    "Recreate collection and run full reingest. "
                    f"dense={sorted(dense_names)} sparse={sorted(sparse_names)}"
                )
                return 1
            print("  [OK] Existing collection schema includes required vectors.")
        else:
            print("  Nothing to do.")
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
        "metadata.source_type",
        "metadata.topic",
        "metadata.doc_type",
        "metadata.jurisdiction",
        "metadata.audience",
        "metadata.language",
    ]:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as e:
            print(f"  Warning: Could not create index {field}: {e}")

    for field in ["metadata.order", "metadata.chunk_id"]:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.INTEGER,
            )
        except Exception as e:
            print(f"  Warning: Could not create index {field}: {e}")

    if getattr(args, "require_colbert", False):
        info = client.get_collection(collection_name)
        missing, dense_names, sparse_names = _schema_requirements_status(
            info,
            require_colbert=True,
        )
        if missing:
            print(
                "  [FAIL] Created collection schema drift: missing "
                f"{', '.join(sorted(missing))}. "
                f"dense={sorted(dense_names)} sparse={sorted(sparse_names)}"
            )
            return 1

    print(f"  Bootstrap completed: {collection_name}")
    return 0


async def cmd_reprocess(args: argparse.Namespace) -> int:
    """Reprocess a specific file or all errors."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.state_manager import UnifiedStateManager

    async def _tracking_tables(pool) -> list[str]:
        rows = await pool.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename LIKE 'unified\\_\\_ingest\\_%\\_\\_cocoindex\\_tracking' ESCAPE '\\'
            """
        )
        return [row["tablename"] for row in rows]

    async def _purge_tracking_rows(pool, source_paths: list[str]) -> int:
        if not source_paths:
            return 0

        total_deleted = 0
        source_keys = [f'"{source_path}"' for source_path in source_paths]
        for table_name in await _tracking_tables(pool):
            if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
                raise ValueError(f"Unexpected tracking table name: {table_name}")
            deleted = await pool.execute(
                f"DELETE FROM {table_name} WHERE source_key = ANY($1::jsonb[])",
                source_keys,
            )
            total_deleted += int(deleted.split()[-1])
        return total_deleted

    def _touch_source_files(sync_dir: Path, source_paths: list[str]) -> int:
        touched = 0
        for source_path in source_paths:
            relative = Path(source_path)
            candidates = [
                relative,
                sync_dir / relative,
                sync_dir.parent / relative,
            ]
            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
                    candidate.touch()
                    touched += 1
                    break
        return touched

    config = UnifiedConfig()
    manager = UnifiedStateManager(database_url=config.database_url)

    try:
        pool = await manager._get_pool()

        if args.file_id:
            rows = await pool.fetch(
                "SELECT source_path FROM ingestion_state WHERE file_id = $1",
                args.file_id,
            )
            source_paths = [row["source_path"] for row in rows if row["source_path"]]
            await pool.execute(
                "UPDATE ingestion_state SET status = 'pending', retry_count = 0, "
                "retry_after = NULL, error_message = NULL WHERE file_id = $1",
                args.file_id,
            )
            purged = await _purge_tracking_rows(pool, source_paths)
            touched = _touch_source_files(config.sync_dir, source_paths)
            print(
                f"Reset file: {args.file_id} "
                f"(purged tracking rows: {purged}, touched files: {touched})"
            )
        else:
            target_status = "error" if args.errors else "pending" if args.pending else None
            if target_status is None:
                print("Specify --file-id, --errors, or --pending")
                return 1

            rows = await pool.fetch(
                "SELECT source_path FROM ingestion_state WHERE status = $1",
                target_status,
            )
            source_paths = [row["source_path"] for row in rows if row["source_path"]]
            result = await pool.execute(
                "UPDATE ingestion_state SET status = 'pending', retry_count = 0, "
                "retry_after = NULL, error_message = NULL WHERE status = $1",
                target_status,
            )
            purged = await _purge_tracking_rows(pool, source_paths)
            touched = _touch_source_files(config.sync_dir, source_paths)
            print(
                f"Reset {target_status} files: {result} "
                f"(purged tracking rows: {purged}, touched files: {touched})"
            )
    finally:
        await manager.close()

    return 0


def cmd_backfill_colbert(args: argparse.Namespace) -> int:
    """Backfill missing ColBERT vectors for points in existing collection."""
    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    checkpoint_path = config.effective_manifest_dir() / ".colbert_backfill_checkpoint.json"

    runner = ColbertBackfillRunner(
        collection_name=config.collection_name,
        qdrant_url=config.qdrant_url,
        qdrant_api_key=config.qdrant_api_key,
        bge_m3_url=config.bge_m3_url,
        bge_m3_timeout=config.bge_m3_timeout,
        checkpoint_path=checkpoint_path,
    )
    try:
        stats = runner.run(
            batch_size=getattr(args, "batch_size", 32),
            limit=getattr(args, "limit", None),
            dry_run=getattr(args, "dry_run", False),
            resume=getattr(args, "resume", False),
        )
    except Exception as exc:
        print(f"  [FAIL] ColBERT backfill failed: {exc}")
        return 1
    finally:
        runner.close()

    print("\n=== ColBERT Backfill ===")
    if getattr(args, "dry_run", False):
        print("  Mode: dry-run (vectors are not written)")
    print(f"  Collection: {config.collection_name}")
    print(f"  scanned={stats.scanned}")
    print(f"  processed={stats.processed}")
    print(f"  skipped={stats.skipped}")
    print(f"  failed={stats.failed}")
    print(f"  qps={getattr(stats, 'qps', 0.0):.2f}")
    print(f"  error_rate={getattr(stats, 'error_rate', 0.0) * 100:.2f}%")
    print(f"  bge_latency_ms={getattr(stats, 'bge_latency_ms', 0.0):.1f}")
    print(f"  qdrant_latency_ms={getattr(stats, 'qdrant_latency_ms', 0.0):.1f}")
    print(f"  checkpoint={checkpoint_path}")
    errors = getattr(stats, "errors", [])
    if errors:
        print("  sample_errors:")
        for message in errors[:5]:
            print(f"    - {message}")

    return 0 if stats.failed == 0 else 2


async def cmd_coverage_check(args: argparse.Namespace) -> int:
    """Check ColBERT coverage ratio in collection."""
    from qdrant_client import QdrantClient

    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    client = QdrantClient(
        url=os.getenv("QDRANT_URL", config.qdrant_url),
        api_key=os.getenv("QDRANT_API_KEY") or config.qdrant_api_key,
        timeout=60,
    )

    try:
        covered, total, ratio = compute_colbert_coverage(client, config.collection_name)
    except Exception as exc:
        print(f"  [FAIL] Coverage check failed: {exc}")
        return 1

    required_ratio = float(getattr(args, "min_ratio", 0.995))
    print(f"\n=== ColBERT Coverage: {config.collection_name} ===")
    print(f"  Coverage: {covered}/{total} ({ratio * 100:.2f}%)")
    print(f"  Threshold: {required_ratio * 100:.2f}%")

    if ratio < required_ratio:
        print("  [FAIL] Coverage below threshold")
        return 1

    print("  [OK] Coverage threshold satisfied")
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

    # reprocess
    reprocess_p = subparsers.add_parser("reprocess", help="Reprocess files")
    reprocess_p.add_argument("--file-id", help="Specific file ID")
    reprocess_p.add_argument("--errors", action="store_true", help="All error files")
    reprocess_p.add_argument("--pending", action="store_true", help="All pending files")

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
    if args.command == "schema-check":
        return asyncio.run(cmd_schema_check(args))
    if args.command == "coverage-check":
        return asyncio.run(cmd_coverage_check(args))
    if args.command == "backfill-colbert":
        return cmd_backfill_colbert(args)
    if args.command == "reprocess":
        return asyncio.run(cmd_reprocess(args))

    return 1


if __name__ == "__main__":
    sys.exit(main())
