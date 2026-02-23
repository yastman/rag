"""Backfill ColBERT multivectors for existing Qdrant points."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, cast

from qdrant_client import QdrantClient, models

from telegram_bot.services.bge_m3_client import BGEM3SyncClient


logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class BackfillStats:
    """Runtime metrics for ColBERT backfill."""

    scanned: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    batches: int = 0
    bge_latency_ms: float = 0.0
    qdrant_latency_ms: float = 0.0
    started_at: float = field(default_factory=time.perf_counter)
    errors: list[str] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return max(time.perf_counter() - self.started_at, 1e-9)

    @property
    def qps(self) -> float:
        return self.scanned / self.elapsed_seconds

    @property
    def error_rate(self) -> float:
        return self.failed / self.scanned if self.scanned else 0.0


def inspect_collection_schema(
    qdrant_client: QdrantClient,
    collection_name: str,
) -> dict[str, set[str]]:
    """Inspect named vector schema for collection."""
    info = qdrant_client.get_collection(collection_name)
    dense_vectors = info.config.params.vectors
    sparse_vectors = info.config.params.sparse_vectors or {}
    dense_names = set(dense_vectors.keys()) if isinstance(dense_vectors, dict) else set()
    sparse_names = set(sparse_vectors.keys()) if isinstance(sparse_vectors, dict) else set()

    return {
        "dense_names": dense_names,
        "sparse_names": sparse_names,
        "missing_dense": {"dense"} - dense_names,
        "missing_sparse": {"bm42"} - sparse_names,
        "missing_colbert": {"colbert"} - dense_names,
    }


def compute_colbert_coverage(
    qdrant_client: QdrantClient,
    collection_name: str,
) -> tuple[int, int, float]:
    """Return (colbert_points, total_points, ratio)."""
    total = qdrant_client.count(collection_name=collection_name).count
    if total == 0:
        return 0, 0, 1.0

    colbert_count = qdrant_client.count(
        collection_name=collection_name,
        count_filter=models.Filter(must=[models.HasVectorCondition(has_vector="colbert")]),
        exact=True,
    ).count
    return colbert_count, total, colbert_count / total


class ColbertBackfillRunner:
    """Batch backfill of missing ColBERT vectors."""

    def __init__(
        self,
        *,
        collection_name: str,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        bge_m3_url: str | None = None,
        bge_m3_timeout: float = 300.0,
        checkpoint_path: Path | None = None,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        qdrant_client: QdrantClient | None = None,
        bge_client: BGEM3SyncClient | Any | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.checkpoint_path = checkpoint_path
        self._qdrant = qdrant_client or QdrantClient(
            url=qdrant_url or "http://localhost:6333",
            api_key=qdrant_api_key,
            timeout=120,
        )
        self._bge = bge_client or BGEM3SyncClient(
            base_url=bge_m3_url or "http://localhost:8000",
            timeout=bge_m3_timeout,
        )

    def run(
        self,
        *,
        batch_size: int = 32,
        limit: int | None = None,
        dry_run: bool = False,
        resume: bool = False,
    ) -> BackfillStats:
        """Execute backfill and return runtime stats."""
        self._ensure_colbert_schema()
        stats = BackfillStats()

        start_offset = self._load_checkpoint_offset() if resume else None
        if resume and start_offset is not None:
            logger.info("Backfill resume from checkpoint offset=%r", start_offset)

        collection_info = self._qdrant.get_collection(self.collection_name)
        total_points = collection_info.points_count or 0
        target_total = (
            min(limit, total_points) if limit is not None and total_points else total_points
        )

        exhausted_collection = False
        offset = start_offset

        while True:
            remaining = None if limit is None else max(limit - stats.scanned, 0)
            if remaining == 0:
                break
            page_size = batch_size if remaining is None else min(batch_size, remaining)
            if page_size <= 0:
                break

            def _scroll_page(
                page_size_value: int = page_size,
                scroll_offset: Any = offset,
            ) -> tuple[list[Any], Any]:
                return self._qdrant.scroll(
                    collection_name=self.collection_name,
                    limit=page_size_value,
                    offset=scroll_offset,
                    with_payload=["page_content", "text"],
                    with_vectors=["colbert"],
                )

            records, next_offset = self._call_with_retry("qdrant.scroll", _scroll_page)

            if not records:
                if next_offset is None:
                    exhausted_collection = True
                break

            stats.batches += 1
            ids_to_update: list[str | int | uuid.UUID] = []
            texts: list[str] = []

            for record in records:
                stats.scanned += 1
                if self._has_colbert_vector(record):
                    stats.skipped += 1
                    continue

                text = self._extract_text(record)
                if not text:
                    stats.failed += 1
                    self._append_error(
                        stats,
                        f"point_id={record.id}: missing payload.page_content/payload.text",
                    )
                    continue

                ids_to_update.append(record.id)
                texts.append(text)

            if ids_to_update:
                if dry_run:
                    stats.processed += len(ids_to_update)
                else:
                    try:
                        bge_started = time.perf_counter()

                        def _encode_batch(
                            texts_batch: list[str] = texts,
                        ) -> list[list[list[float]]]:
                            return self._encode_colbert(texts_batch)

                        colbert_vecs = self._call_with_retry("bge.encode_colbert", _encode_batch)
                        stats.bge_latency_ms += (time.perf_counter() - bge_started) * 1000

                        if len(colbert_vecs) != len(ids_to_update):
                            raise RuntimeError(
                                "BGE-M3 returned mismatched colbert vectors: "
                                f"{len(colbert_vecs)} != {len(ids_to_update)}"
                            )

                        points = [
                            models.PointVectors(id=point_id, vector={"colbert": colbert_vec})
                            for point_id, colbert_vec in zip(
                                ids_to_update, colbert_vecs, strict=True
                            )
                        ]
                        qdrant_started = time.perf_counter()

                        def _update_batch(points_batch: list[Any] = points) -> Any:
                            return self._qdrant.update_vectors(
                                collection_name=self.collection_name,
                                points=points_batch,
                            )

                        self._call_with_retry("qdrant.update_vectors", _update_batch)
                        stats.qdrant_latency_ms += (time.perf_counter() - qdrant_started) * 1000
                        stats.processed += len(points)
                    except Exception as exc:
                        stats.failed += len(ids_to_update)
                        self._append_error(stats, f"batch update failed: {exc}")

            self._save_checkpoint(next_offset=next_offset, last_point_id=records[-1].id)
            self._log_progress(stats=stats, target_total=target_total)

            if next_offset is None:
                exhausted_collection = True
                break
            offset = next_offset

        if exhausted_collection:
            self._clear_checkpoint()

        return stats

    def close(self) -> None:
        """Close resources."""
        close_fn = getattr(self._bge, "close", None)
        if callable(close_fn):
            close_fn()

    def _ensure_colbert_schema(self) -> None:
        schema = inspect_collection_schema(self._qdrant, self.collection_name)
        if schema["missing_colbert"]:
            raise RuntimeError(
                f"Qdrant collection '{self.collection_name}' missing required vector 'colbert'"
            )

    @staticmethod
    def _has_colbert_vector(record: Any) -> bool:
        vector = getattr(record, "vector", None)
        if not isinstance(vector, dict):
            return False
        colbert = vector.get("colbert")
        return bool(colbert)

    @staticmethod
    def _extract_text(record: Any) -> str:
        payload = getattr(record, "payload", {}) or {}
        if not isinstance(payload, dict):
            return ""
        for key in ("page_content", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _encode_colbert(self, texts: list[str]) -> list[list[list[float]]]:
        if hasattr(self._bge, "encode_colbert"):
            result = self._bge.encode_colbert(texts)
            return cast(list[list[list[float]]], result.colbert_vecs)

        if hasattr(self._bge, "encode_hybrid"):
            result = self._bge.encode_hybrid(texts)
            colbert_vecs = result.colbert_vecs
            if colbert_vecs is None:
                raise RuntimeError("BGE-M3 encode_hybrid response missing colbert_vecs")
            return cast(list[list[list[float]]], colbert_vecs)

        raise RuntimeError("BGE-M3 client does not provide encode_colbert or encode_hybrid")

    def _call_with_retry(self, name: str, fn: Callable[[], T]) -> T:
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return fn()
            except Exception:
                if attempt >= self.retry_attempts:
                    raise
                delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "%s failed (attempt %d/%d), retrying in %.2fs",
                    name,
                    attempt,
                    self.retry_attempts,
                    delay,
                )
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError(f"{name} retry loop ended unexpectedly")

    @staticmethod
    def _append_error(stats: BackfillStats, message: str) -> None:
        if len(stats.errors) < 20:
            stats.errors.append(message)
        logger.warning("ColBERT backfill: %s", message)

    def _log_progress(self, *, stats: BackfillStats, target_total: int) -> None:
        eta_seconds: float | None = None
        if target_total > 0 and stats.qps > 0:
            remaining = max(target_total - stats.scanned, 0)
            eta_seconds = remaining / stats.qps
        eta_str = f"{eta_seconds:.1f}s" if eta_seconds is not None else "n/a"

        logger.info(
            "ColBERT backfill progress: scanned=%d processed=%d skipped=%d failed=%d "
            "qps=%.2f error_rate=%.2f%% eta=%s bge_ms=%.1f qdrant_ms=%.1f",
            stats.scanned,
            stats.processed,
            stats.skipped,
            stats.failed,
            stats.qps,
            stats.error_rate * 100,
            eta_str,
            stats.bge_latency_ms,
            stats.qdrant_latency_ms,
        )

    def _load_checkpoint_offset(self) -> int | str | uuid.UUID | None:
        if self.checkpoint_path is None or not self.checkpoint_path.exists():
            return None
        try:
            data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read checkpoint %s: %s", self.checkpoint_path, exc)
            return None

        raw_offset = data.get("next_offset")
        if isinstance(raw_offset, dict) and raw_offset.get("type") == "uuid":
            value = raw_offset.get("value")
            try:
                return uuid.UUID(value)
            except Exception:
                logger.warning("Invalid UUID checkpoint offset: %r", value)
                return None
        if isinstance(raw_offset, (int, str)):
            return raw_offset
        return None

    def _save_checkpoint(self, *, next_offset: Any, last_point_id: Any) -> None:
        if self.checkpoint_path is None:
            return
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "next_offset": self._serialize_offset(next_offset),
            "last_point_id": str(last_point_id) if last_point_id is not None else None,
            "updated_at": int(time.time()),
        }
        self.checkpoint_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def _clear_checkpoint(self) -> None:
        if self.checkpoint_path and self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    @staticmethod
    def _serialize_offset(value: Any) -> Any:
        if value is None or isinstance(value, (int, str)):
            return value
        if isinstance(value, uuid.UUID):
            return {"type": "uuid", "value": str(value)}
        return str(value)
