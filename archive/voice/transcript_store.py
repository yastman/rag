"""PostgreSQL transcript storage for voice calls."""

from __future__ import annotations

import json
import logging
import uuid

import asyncpg

from src.voice.schemas import CallStatus


logger = logging.getLogger(__name__)


class TranscriptStore:
    """Stores call transcripts in PostgreSQL."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    @property
    def _db(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("TranscriptStore not initialized. Call initialize() first.")
        return self._pool

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create_call(
        self,
        phone: str,
        lead_data: dict | None = None,
        callback_chat_id: int | None = None,
        call_id: str | None = None,
    ) -> str:
        call_id = call_id or str(uuid.uuid4())
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO call_transcripts (id, phone, lead_data, callback_chat_id)
                   VALUES ($1, $2, $3, $4)""",
                uuid.UUID(call_id),
                phone,
                json.dumps(lead_data or {}),
                callback_chat_id,
            )
        return call_id

    async def update_status(self, call_id: str, status: CallStatus) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                """UPDATE call_transcripts SET status = $1, updated_at = NOW()
                   WHERE id = $2""",
                status.value,
                uuid.UUID(call_id),
            )

    async def append_transcript(
        self, call_id: str, role: str, text: str, timestamp_ms: int
    ) -> None:
        entry = {"role": role, "text": text, "timestamp_ms": timestamp_ms}
        async with self._db.acquire() as conn:
            await conn.execute(
                """UPDATE call_transcripts
                   SET transcript = transcript || $1::jsonb, updated_at = NOW()
                   WHERE id = $2""",
                json.dumps([entry]),
                uuid.UUID(call_id),
            )

    async def finalize_call(
        self,
        call_id: str,
        duration_sec: int,
        validation_result: dict | None = None,
        langfuse_trace_id: str | None = None,
    ) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                """UPDATE call_transcripts
                   SET status = $1, duration_sec = $2,
                       validation_result = $3, langfuse_trace_id = $4,
                       updated_at = NOW()
                   WHERE id = $5""",
                CallStatus.COMPLETED.value,
                duration_sec,
                json.dumps(validation_result) if validation_result else None,
                langfuse_trace_id,
                uuid.UUID(call_id),
            )

    async def get_call(self, call_id: str) -> dict | None:
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM call_transcripts WHERE id = $1",
                uuid.UUID(call_id),
            )
            return dict(row) if row else None
