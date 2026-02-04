# src/ingestion/unified/state_manager.py
"""State manager using existing Postgres ingestion_state table."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg


@dataclass
class FileState:
    """Maps to ingestion_state table."""

    file_id: str
    source_path: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    modified_time: datetime | None = None
    content_hash: str | None = None
    parser_version: str | None = None
    chunker_version: str | None = None
    embedding_model: str = "voyage-4-large"
    chunk_count: int = 0
    collection_name: str | None = None
    pipeline_version: str = "v3.2.1"
    indexed_at: datetime | None = None
    status: str = "pending"
    error_message: str | None = None
    retry_count: int = 0
    retry_after: datetime | None = None

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "FileState":
        """Create from database row."""
        return cls(**{k: v for k, v in dict(row).items() if k in cls.__dataclass_fields__})


class UnifiedStateManager:
    """Manages ingestion state in Postgres."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        database_url: str | None = None,
    ):
        self._pool = pool
        self._database_url = database_url
        self._owns_pool = pool is None
        # Tables are in public schema of cocoindex database
        self._table = "ingestion_state"
        self._dlq_table = "ingestion_dead_letter"

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            if self._database_url is None:
                raise ValueError("Either pool or database_url required")
            self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)
        return self._pool

    async def close(self) -> None:
        if self._owns_pool and self._pool:
            await self._pool.close()
            self._pool = None

    async def get_state(self, file_id: str) -> FileState | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(f"SELECT * FROM {self._table} WHERE file_id = $1", file_id)
        return FileState.from_row(row) if row else None

    async def upsert_state(self, state: FileState) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"""
            INSERT INTO {self._table} (
                file_id, source_path, file_name, mime_type, file_size,
                modified_time, content_hash, parser_version, chunker_version,
                embedding_model, chunk_count, collection_name, pipeline_version,
                status, error_message, retry_count, retry_after, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW())
            ON CONFLICT (file_id) DO UPDATE SET
                source_path = EXCLUDED.source_path,
                file_name = EXCLUDED.file_name,
                mime_type = EXCLUDED.mime_type,
                file_size = EXCLUDED.file_size,
                modified_time = EXCLUDED.modified_time,
                content_hash = EXCLUDED.content_hash,
                parser_version = EXCLUDED.parser_version,
                chunker_version = EXCLUDED.chunker_version,
                collection_name = EXCLUDED.collection_name,
                pipeline_version = EXCLUDED.pipeline_version,
                status = EXCLUDED.status,
                error_message = EXCLUDED.error_message,
                retry_count = EXCLUDED.retry_count,
                retry_after = EXCLUDED.retry_after,
                updated_at = NOW()
            """,
            state.file_id,
            state.source_path,
            state.file_name,
            state.mime_type,
            state.file_size,
            state.modified_time,
            state.content_hash,
            state.parser_version,
            state.chunker_version,
            state.embedding_model,
            state.chunk_count,
            state.collection_name,
            state.pipeline_version,
            state.status,
            state.error_message,
            state.retry_count,
            state.retry_after,
        )

    async def mark_processing(self, file_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"UPDATE {self._table} SET status = 'processing', updated_at = NOW() WHERE file_id = $1",
            file_id,
        )

    async def mark_indexed(self, file_id: str, chunk_count: int, content_hash: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"""
            UPDATE {self._table}
            SET status = 'indexed', chunk_count = $2, content_hash = $3,
                indexed_at = NOW(), error_message = NULL, retry_count = 0, retry_after = NULL,
                updated_at = NOW()
            WHERE file_id = $1
            """,
            file_id,
            chunk_count,
            content_hash,
        )

    async def mark_error(self, file_id: str, error: str) -> None:
        pool = await self._get_pool()
        # Exponential backoff: 1min, 5min, 30min
        await pool.execute(
            f"""
            UPDATE {self._table}
            SET status = 'error',
                error_message = $2,
                retry_count = retry_count + 1,
                retry_after = NOW() + (INTERVAL '1 minute' * POWER(5, LEAST(retry_count, 3))),
                updated_at = NOW()
            WHERE file_id = $1
            """,
            file_id,
            error[:1000],  # Truncate error message
        )

    async def mark_deleted(self, file_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"UPDATE {self._table} SET status = 'deleted', updated_at = NOW() WHERE file_id = $1",
            file_id,
        )

    async def should_process(self, file_id: str, content_hash: str) -> bool:
        """Check if file needs processing (new or changed)."""
        state = await self.get_state(file_id)
        if state is None:
            return True  # New file
        if state.status == "indexed" and state.content_hash == content_hash:
            return False  # Unchanged
        if state.status == "error" and state.retry_after and state.retry_after > datetime.now(UTC):
            return False  # Still in backoff
        # Exceeded retries means file is in DLQ
        return state.retry_count < 3

    async def get_all_indexed_file_ids(self) -> set[str]:
        pool = await self._get_pool()
        rows = await pool.fetch(f"SELECT file_id FROM {self._table} WHERE status = 'indexed'")
        return {row["file_id"] for row in rows}

    async def add_to_dlq(
        self,
        file_id: str,
        error_type: str,
        error_message: str,
        payload: dict | None = None,
    ) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            f"""
            INSERT INTO {self._dlq_table} (file_id, error_type, error_message, payload)
            VALUES ($1, $2, $3, $4::jsonb) RETURNING id
            """,
            file_id,
            error_type,
            error_message[:2000],
            json.dumps(payload) if payload else None,
        )
        return row["id"]

    async def get_stats(self) -> dict[str, int]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            f"SELECT status, COUNT(*) as count FROM {self._table} GROUP BY status"
        )
        return {row["status"]: row["count"] for row in rows}

    async def get_dlq_count(self) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(f"SELECT COUNT(*) as count FROM {self._dlq_table}")
        return row["count"]

    # =========================================================================
    # SYNC METHODS (for CocoIndex target connector)
    # =========================================================================
    # These wrap async methods using a dedicated event loop.
    # Safe to call from sync context (e.g., CocoIndex mutate()).
    #
    # IMPORTANT: Each sync call uses a fresh event loop. To avoid asyncpg pool
    # being attached to a closed loop, we reset the pool before each sync call.

    def _run_sync(self, coro):
        """Run coroutine synchronously with a fresh event loop.

        Resets the pool before running to avoid 'Event loop is closed' errors
        when asyncpg pool was created in a previous (now closed) loop.
        """
        # Reset pool to avoid loop mismatch
        if self._pool is not None:
            # Pool exists from previous loop - it's now invalid
            # asyncpg pools cannot be reused across different event loops
            self._pool = None

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            # Close pool before closing loop to release connections properly
            if self._pool is not None:
                loop.run_until_complete(self._pool.close())
                self._pool = None
            loop.close()

    def get_state_sync(self, file_id: str) -> FileState | None:
        """Sync version of get_state()."""
        return self._run_sync(self.get_state(file_id))

    def should_process_sync(self, file_id: str, content_hash: str) -> bool:
        """Sync version of should_process()."""
        return self._run_sync(self.should_process(file_id, content_hash))

    def mark_processing_sync(self, file_id: str) -> None:
        """Sync version of mark_processing()."""
        self._run_sync(self.mark_processing(file_id))

    def mark_indexed_sync(self, file_id: str, chunk_count: int, content_hash: str) -> None:
        """Sync version of mark_indexed()."""
        self._run_sync(self.mark_indexed(file_id, chunk_count, content_hash))

    def mark_error_sync(self, file_id: str, error: str) -> None:
        """Sync version of mark_error()."""
        self._run_sync(self.mark_error(file_id, error))

    def mark_deleted_sync(self, file_id: str) -> None:
        """Sync version of mark_deleted()."""
        self._run_sync(self.mark_deleted(file_id))

    def add_to_dlq_sync(
        self,
        file_id: str,
        error_type: str,
        error_message: str,
        payload: dict | None = None,
    ) -> int:
        """Sync version of add_to_dlq()."""
        return self._run_sync(self.add_to_dlq(file_id, error_type, error_message, payload))
