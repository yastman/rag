# src/ingestion/unified/targets/qdrant_hybrid_target.py
"""CocoIndex custom target connector for Qdrant hybrid search.

This target connector receives mutations from CocoIndex and:
1. Parses documents via DoclingClient
2. Generates embeddings (BGE-M3 dense + sparse, or Voyage dense + BGE-M3 sparse)
3. Writes to Qdrant with payload contract
4. Updates state in Postgres
"""

import dataclasses
import hashlib
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from cocoindex.op import TargetSpec, target_connector

from src.ingestion.docling_client import DoclingClient, DoclingConfig
from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter
from src.ingestion.unified.state_manager import FileState, UnifiedStateManager


logger = logging.getLogger(__name__)


def compute_content_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


class QdrantHybridTargetSpec(TargetSpec):
    """Configuration for Qdrant hybrid target."""

    ***REMOVED***
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_name: str = "gdrive_documents_bge"

    # Docling
    docling_url: str = "http://localhost:5001"
    docling_timeout: float = 300.0
    max_tokens_per_chunk: int = 512

    ***REMOVED***
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-4-large"

    # Local embeddings (BGE-M3 dense + sparse)
    use_local_embeddings: bool = False
    bge_m3_url: str = "http://localhost:8000"
    bge_m3_timeout: float = 300.0
    bge_m3_concurrency: int = 1

    # Postgres
    database_url: str = "postgresql://postgres:postgres@localhost:5432/cocoindex"

    # Pipeline
    max_retries: int = 3
    pipeline_version: str = "v3.2.1"

    @classmethod
    def from_config(cls, config: UnifiedConfig) -> "QdrantHybridTargetSpec":
        """Create spec from UnifiedConfig."""
        return cls(
            qdrant_url=config.qdrant_url,
            qdrant_api_key=config.qdrant_api_key,
            collection_name=config.collection_name,
            docling_url=config.docling_url,
            docling_timeout=config.docling_timeout,
            max_tokens_per_chunk=config.max_tokens_per_chunk,
            voyage_api_key=config.voyage_api_key,
            voyage_model=config.voyage_model,
            use_local_embeddings=config.use_local_embeddings,
            bge_m3_url=config.bge_m3_url,
            bge_m3_timeout=config.bge_m3_timeout,
            bge_m3_concurrency=config.bge_m3_concurrency,
            database_url=config.database_url,
            max_retries=config.max_retries,
            pipeline_version=config.pipeline_version,
        )


@dataclasses.dataclass
class QdrantHybridTargetValues:
    """Value type for mutations from CocoIndex flow."""

    abs_path: str
    source_path: str
    file_name: str
    mime_type: str
    file_size: int


@target_connector(
    spec_cls=QdrantHybridTargetSpec,
    persistent_key_type=str,
)
class QdrantHybridTargetConnector:
    """CocoIndex target connector for Qdrant hybrid search.

    Handles:
    - Document parsing via Docling
    - Embedding generation (BGE-M3 dense + sparse, or Voyage dense + BGE-M3 sparse)
    - Qdrant upsert with payload contract
    - Postgres state tracking
    """

    # Shared resources (initialized lazily)
    # Note: StateManager is created fresh per mutate() call to avoid asyncpg pool issues
    _writer: QdrantHybridWriter | None = None
    _docling: DoclingClient | None = None
    _writer_lock = threading.Lock()
    _docling_lock = threading.Lock()

    # Sequential processing: Semaphore(1) ensures only one file is processed at a time.
    # Critical for CPU-only VPS where BGE-M3 is slow (~10-50s per batch).
    # Without this, CocoIndex sends parallel requests → queue grows → timeouts.
    _process_semaphore = threading.Semaphore(1)

    @staticmethod
    def get_persistent_key(spec: QdrantHybridTargetSpec, _target_name: str) -> str:
        """Return unique identifier for this target instance."""
        return f"{spec.collection_name}@{spec.qdrant_url}"

    @staticmethod
    def describe(key: str) -> str:
        """Human-readable description."""
        return f"Qdrant Hybrid Target: {key}"

    @staticmethod
    def apply_setup_change(
        key: str,
        previous: QdrantHybridTargetSpec | None,
        current: QdrantHybridTargetSpec | None,
    ) -> None:
        """Apply setup changes (create/delete target infrastructure)."""
        if previous is None and current is not None:
            logger.info(f"Target created: {key}")
        elif previous is not None and current is None:
            logger.info(f"Target removed: {key}")
        else:
            logger.info(f"Target updated: {key}")

    @staticmethod
    def prepare(spec: QdrantHybridTargetSpec) -> QdrantHybridTargetSpec:
        """Prepare for execution (called once before mutations)."""
        return spec

    @classmethod
    def _get_writer(cls, spec: QdrantHybridTargetSpec) -> QdrantHybridWriter:
        """Get or create QdrantHybridWriter."""
        if cls._writer is None:
            with cls._writer_lock:
                if cls._writer is None:
                    cls._writer = QdrantHybridWriter(
                        qdrant_url=spec.qdrant_url,
                        qdrant_api_key=spec.qdrant_api_key,
                        voyage_api_key=spec.voyage_api_key or os.getenv("VOYAGE_API_KEY", ""),
                        voyage_model=spec.voyage_model,
                        use_local_embeddings=spec.use_local_embeddings,
                        bge_m3_url=spec.bge_m3_url,
                        bge_m3_timeout=spec.bge_m3_timeout,
                        bge_m3_concurrency=spec.bge_m3_concurrency,
                    )
        return cls._writer

    @classmethod
    def _get_docling(cls, spec: QdrantHybridTargetSpec) -> DoclingClient:
        """Get or create DoclingClient."""
        if cls._docling is None:
            with cls._docling_lock:
                if cls._docling is None:
                    config = DoclingConfig(
                        base_url=spec.docling_url,
                        timeout=spec.docling_timeout,
                        max_tokens=spec.max_tokens_per_chunk,
                    )
                    cls._docling = DoclingClient(config)
        return cls._docling

    @classmethod
    def mutate(
        cls,
        *all_mutations: tuple[QdrantHybridTargetSpec, dict[str, QdrantHybridTargetValues | None]],
    ) -> None:
        """Apply data mutations to Qdrant (fully synchronous, sequential).

        For each file_id:
        - None value: delete all points for file_id
        - Non-None value: parse, embed, upsert (replace semantics)

        Creates fresh StateManager per mutate() call to avoid asyncpg pool
        being attached to closed event loops between CocoIndex batches.

        NOTE: Uses Semaphore(1) for sequential processing on CPU-only VPS.
        """
        # Acquire semaphore to ensure sequential processing (one file at a time)
        with cls._process_semaphore:
            logger.info(f"mutate(): {len(all_mutations)} batch(es)")
            for spec, mutations in all_mutations:
                logger.info(f"Batch: {len(mutations)} mutations, collection={spec.collection_name}")
                # Create fresh state manager for this batch (not cached)
                # This avoids asyncpg pool issues with different event loops
                state_manager = UnifiedStateManager(database_url=spec.database_url)
                logger.debug("Created state_manager, entering sync_context...")

                with state_manager.sync_context():
                    logger.debug(f"Inside sync_context, iterating {len(mutations)} mutations...")
                    for file_id, mutation in mutations.items():
                        logger.debug(
                            f"Processing mutation: file_id={file_id}, has_value={mutation is not None}"
                        )
                        try:
                            if mutation is None:
                                QdrantHybridTargetConnector._handle_delete_with_state(
                                    spec, file_id, state_manager
                                )
                            else:
                                QdrantHybridTargetConnector._handle_upsert_with_state(
                                    spec, file_id, mutation, state_manager
                                )
                        except Exception as e:
                            logger.error(f"Mutation failed for {file_id}: {e}", exc_info=True)
                            # Don't raise — one failing file must not kill the entire
                            # ingestion process.  The error is already tracked in
                            # StateManager (mark_error_sync / DLQ).

    @classmethod
    def _handle_delete_with_state(
        cls, spec: QdrantHybridTargetSpec, file_id: str, state_manager: UnifiedStateManager
    ) -> None:
        """Handle file deletion (sync)."""
        writer = cls._get_writer(spec)

        writer.delete_file_sync(file_id, spec.collection_name)
        state_manager.mark_deleted_sync(file_id)
        logger.debug(f"Deleted: file_id={file_id}")

    @classmethod
    def _handle_upsert_with_state(
        cls,
        spec: QdrantHybridTargetSpec,
        file_id: str,
        mutation: QdrantHybridTargetValues,
        state_manager: UnifiedStateManager,
    ) -> None:
        """Handle file insert/update (sync)."""
        logger.debug(f"Upsert: file_id={file_id}, path={mutation.abs_path}")

        writer = cls._get_writer(spec)
        docling = cls._get_docling(spec)

        abs_path = Path(mutation.abs_path)
        source_path = mutation.source_path

        # Compute content hash
        content_hash = compute_content_hash(abs_path)
        logger.debug(f"Hash: {content_hash}")

        # Check if processing needed (skip unchanged)
        if not state_manager.should_process_sync(file_id, content_hash):
            logger.debug(f"Skipping unchanged: {source_path}")
            return

        # Persist metadata before processing so state table keeps source/file context.
        state_manager.upsert_state_sync(
            FileState(
                file_id=file_id,
                source_path=source_path,
                file_name=mutation.file_name,
                mime_type=mutation.mime_type,
                file_size=mutation.file_size,
                content_hash=content_hash,
                embedding_model="bge-m3-api" if spec.use_local_embeddings else spec.voyage_model,
                collection_name=spec.collection_name,
                pipeline_version=spec.pipeline_version,
                status="processing",
            )
        )

        try:
            # Parse and chunk (sync)
            docling_chunks = docling.chunk_file_sync(abs_path)
            if not docling_chunks:
                state_manager.mark_indexed_sync(file_id, 0, content_hash)
                logger.warning(f"No chunks from: {source_path}")
                return

            # Convert to ingestion chunks
            chunks = docling.to_ingestion_chunks(
                docling_chunks,
                source=source_path,
                source_type=abs_path.suffix.lstrip("."),
            )

            # File metadata
            file_metadata = {
                "file_name": mutation.file_name,
                "mime_type": mutation.mime_type,
                "file_size": mutation.file_size,
                "content_hash": content_hash,
                "modified_time": datetime.now(UTC).isoformat(),
            }

            # Write to Qdrant (sync)
            stats = writer.upsert_chunks_sync(
                chunks=chunks,
                file_id=file_id,
                source_path=source_path,
                file_metadata=file_metadata,
                collection_name=spec.collection_name,
            )

            if stats.errors:
                raise Exception("; ".join(stats.errors))

            # Update state
            state_manager.mark_indexed_sync(file_id, stats.points_upserted, content_hash)
            logger.info(f"Indexed: {source_path} ({stats.points_upserted} chunks)")

        except Exception as e:
            logger.error(f"Upsert failed for {source_path}: {e}")
            state_manager.mark_error_sync(file_id, str(e))

            # Check DLQ
            state = state_manager.get_state_sync(file_id)
            if state and state.retry_count >= spec.max_retries:
                state_manager.add_to_dlq_sync(
                    file_id=file_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    payload={"source_path": source_path},
                )
                logger.warning(f"Moved to DLQ: {source_path}")
            # Don't raise — error is tracked in state/DLQ, process continues
