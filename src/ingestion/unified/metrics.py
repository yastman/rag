# src/ingestion/unified/metrics.py
"""Structured metrics logging for unified ingestion pipeline."""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class IngestionMetrics:
    """Metrics for a single file ingestion."""

    file_id: str
    source_path: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Timing
    docling_duration_ms: float = 0
    voyage_duration_ms: float = 0
    qdrant_duration_ms: float = 0
    total_duration_ms: float = 0

    # Counts
    chunks_created: int = 0
    chunks_deleted: int = 0

    # Status
    status: str = "pending"  # pending, success, error, skipped
    error_message: str | None = None

    def to_structured_log(self) -> dict[str, Any]:
        """Convert to structured log dict."""
        return {
            "event": "ingestion_file",
            "file_id": self.file_id,
            "source_path": self.source_path,
            "status": self.status,
            "chunks_created": self.chunks_created,
            "chunks_deleted": self.chunks_deleted,
            "docling_ms": round(self.docling_duration_ms, 1),
            "voyage_ms": round(self.voyage_duration_ms, 1),
            "qdrant_ms": round(self.qdrant_duration_ms, 1),
            "total_ms": round(self.total_duration_ms, 1),
            "error": self.error_message,
            "timestamp": self.started_at.isoformat(),
        }


@contextmanager
def timed_operation(metrics: IngestionMetrics, operation: str):
    """Context manager to time an operation and store in metrics.

    Args:
        metrics: IngestionMetrics instance to update
        operation: One of 'docling', 'voyage', 'qdrant'

    Usage:
        with timed_operation(metrics, 'docling'):
            chunks = await docling.chunk_file(path)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        attr = f"{operation}_duration_ms"
        if hasattr(metrics, attr):
            setattr(metrics, attr, duration_ms)


def log_ingestion_result(metrics: IngestionMetrics) -> None:
    """Log ingestion result as structured JSON."""
    log_data = metrics.to_structured_log()

    if metrics.status == "success":
        logger.info(
            f"Ingested {metrics.source_path}: {metrics.chunks_created} chunks "
            f"(docling={metrics.docling_duration_ms:.0f}ms, "
            f"voyage={metrics.voyage_duration_ms:.0f}ms, "
            f"qdrant={metrics.qdrant_duration_ms:.0f}ms)",
            extra={"structured": log_data},
        )
    elif metrics.status == "skipped":
        logger.debug(
            f"Skipped unchanged: {metrics.source_path}",
            extra={"structured": log_data},
        )
    elif metrics.status == "error":
        logger.error(
            f"Failed {metrics.source_path}: {metrics.error_message}",
            extra={"structured": log_data},
        )


def log_batch_summary(
    processed: int,
    skipped: int,
    failed: int,
    deleted: int,
    total_duration_ms: float,
) -> None:
    """Log batch summary."""
    logger.info(
        f"Batch complete: processed={processed}, skipped={skipped}, "
        f"failed={failed}, deleted={deleted}, duration={total_duration_ms:.0f}ms",
        extra={
            "structured": {
                "event": "ingestion_batch",
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "deleted": deleted,
                "total_ms": round(total_duration_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        },
    )
