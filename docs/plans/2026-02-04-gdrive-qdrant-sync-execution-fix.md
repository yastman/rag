# GDrive → Qdrant Sync Execution Fix

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix async/sync mismatch in target connector to enable end-to-end pipeline execution.

**Architecture:** CocoIndex calls `mutate()` synchronously → handlers must be sync → use existing `*_sync` methods in writer, add sync wrappers to StateManager and DoclingClient.

**Tech Stack:** Python 3.12, CocoIndex 0.3.28, asyncpg, httpx, Qdrant, Voyage AI

---

## Промт для новой сессии

```
Выполни план: docs/plans/2026-02-04-gdrive-qdrant-sync-execution-fix.md

КОНТЕКСТ:
- Unified ingestion pipeline v3.2.1 почти готов, но target connector использует asyncio.run() с async handlers
- CocoIndex вызывает mutate() синхронно — нужно сделать всё sync
- rclone работает, 15 файлов в ~/drive-sync/, Docker сервисы запущены
- 2 теста падают: test_target_sync_execution.py

ЗАДАЧИ (последовательно):
1. StateManager: добавить *_sync() методы + тест
2. DoclingClient: добавить chunk_file_sync() + тест
3. Target connector: рефакторинг на pure sync (убрать asyncio.run)
4. E2E валидация: запустить ingestion, проверить Qdrant

ОГРАНИЧЕНИЯ:
- НЕ использовать asyncio.run() в mutate()
- НЕ создавать новый event loop на каждый sync-метод если есть кэшированные ресурсы
- Использовать asyncio.Runner (Python 3.11+) или один loop на весь mutate()
- Закрывать async-ресурсы после обработки

КРИТЕРИИ ПРИЁМКИ:
- pytest tests/unit/ingestion/test_target_sync_execution.py -v → 3 passed
- pytest tests/unit/ingestion/ -v → all pass
- uv run python -m src.ingestion.unified.cli run → индексирует файлы
- curl localhost:6333/collections/gdrive_documents_scalar → points_count > 0

SKILLS: superpowers:executing-plans, superpowers:verification-before-completion

НЕ делай git push. Коммить после каждой задачи.
```

---

## ТЗ (обязательные требования)

### Цель

Починить async/sync mismatch в target connector так, чтобы unified ingestion pipeline выполнялся end-to-end
(файлы из `~/drive-sync/` индексируются в Qdrant) и unit-тесты по sync execution проходили.

### Проблема

`cocoindex` вызывает `TargetConnector.mutate()` **синхронно**. Текущая реализация опирается на `asyncio.run()` и
async handlers, из-за чего получаем конфликты event loop и блокировку пайплайна.

### Ключевые ограничения (важно)

- `mutate()` и все методы, вызываемые CocoIndex внутри `mutate()`, должны быть **синхронными** (не coroutine).
- Запрещено использовать `asyncio.run(` (это проверяется тестом).
- Нельзя создавать/переиспользовать `asyncpg.Pool` и/или `httpx.AsyncClient` между **разными** event loop'ами.
  Это приводит к ошибкам вида `Future attached to a different loop` и к утечкам незакрытых соединений.
- Если добавляются `*_sync()` методы к async-компонентам (StateManager/DoclingClient), то они должны:
  - выполняться в **одном** runner/loop в рамках вызова `mutate()` (или на экземпляр адаптера),
  - создавать async-ресурсы (pool/client) **в этом же loop** и корректно закрывать их в конце.

Практически допустимые варианты реализации sync-моста:

1) **Рекомендуется:** один `asyncio.Runner` (Python 3.11+) на весь вызов `mutate()`; все async-вызовы гоняются через
   `runner.run(...)`, а ресурсы создаются/закрываются внутри того же runner.
2) Background thread с event loop + `asyncio.run_coroutine_threadsafe` (если нужен reuse между вызовами).

> Важно: не копировать подход “`asyncio.new_event_loop()` на каждый sync-метод” при наличии кэшируемых async-ресурсов
> (`self._pool`, `self._client`). Это почти гарантированно ломает asyncpg/httpx из-за привязки к loop.

### Объём работ (Definition of Done)

- `QdrantHybridTargetConnector.mutate()` — полностью sync, без `asyncio.run(`.
- `_handle_delete()` и `_handle_upsert()` — обычные sync-методы (не coroutine), без скрытых async-await.
- Сохранить payload contract и replace semantics (delete → upsert) из текущего writer.
- Закрывать async-ресурсы (docling client, asyncpg pool) после обработки пачки мутаций.

### Критерии приёмки

- `uv run pytest tests/unit/ingestion/test_target_sync_execution.py -v` проходит.
- `uv run pytest tests/unit/ingestion/ -v` проходит.
- `uv run python -m src.ingestion.unified.cli run` индексирует хотя бы 1 файл (коллекция `gdrive_documents_scalar`
  имеет `points_count > 0`).
- В логах нет `Future attached to a different loop` и нет предупреждений про незакрытые http/db соединения.

### Техстек

Python `>=3.11` (repo targets `py311`), CocoIndex `0.3.28`, asyncpg, httpx, Qdrant, Voyage AI.

---

## Current State

- **rclone:** ✅ Working, 15 files in `~/drive-sync/`
- **Docker services:** ✅ postgres, qdrant, docling running
- **Code:** Target connector uses `asyncio.run()` with async handlers
- **Tests:** 2 failing in `test_target_sync_execution.py`
- **Data:** 0 files ingested (pipeline blocked by async/sync issue)

## Files to Modify

| File | Change |
|------|--------|
| `src/ingestion/unified/state_manager.py` | Add `*_sync()` methods |
| `src/ingestion/docling_client.py` | Add `chunk_file_sync()` |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | Refactor to pure sync |
| `tests/unit/ingestion/test_target_sync_execution.py` | Update test expectations |

---

## Task 1: Add StateManager Sync Methods

**Files:**
- Modify: `src/ingestion/unified/state_manager.py`
- Test: `tests/unit/ingestion/test_state_manager_sync.py` (create)

### Step 1.1: Write the failing test

Create `tests/unit/ingestion/test_state_manager_sync.py`:

```python
# tests/unit/ingestion/test_state_manager_sync.py
"""Tests for sync methods in UnifiedStateManager."""

import asyncio


class TestStateManagerSyncMethods:
    """Verify sync methods exist and are not coroutines."""

    def test_sync_methods_exist(self):
        """All required sync methods should exist."""
        from src.ingestion.unified.state_manager import UnifiedStateManager

        required_methods = [
            "get_state_sync",
            "should_process_sync",
            "mark_processing_sync",
            "mark_indexed_sync",
            "mark_error_sync",
            "mark_deleted_sync",
            "add_to_dlq_sync",
        ]

        for method_name in required_methods:
            assert hasattr(UnifiedStateManager, method_name), f"Missing {method_name}"

    def test_sync_methods_are_not_coroutines(self):
        """Sync methods should not be async."""
        from src.ingestion.unified.state_manager import UnifiedStateManager

        sync_methods = [
            "get_state_sync",
            "should_process_sync",
            "mark_processing_sync",
            "mark_indexed_sync",
            "mark_error_sync",
            "mark_deleted_sync",
            "add_to_dlq_sync",
        ]

        for method_name in sync_methods:
            method = getattr(UnifiedStateManager, method_name)
            assert not asyncio.iscoroutinefunction(method), f"{method_name} should be sync"
```

### Step 1.2: Run test to verify it fails

```bash
uv run pytest tests/unit/ingestion/test_state_manager_sync.py -v
```

Expected: FAIL with `AttributeError: type object 'UnifiedStateManager' has no attribute 'get_state_sync'`

### Step 1.3: Implement sync methods

Add to `src/ingestion/unified/state_manager.py` after line 211 (end of class):

```python
    # =========================================================================
    # SYNC METHODS (for CocoIndex target connector)
    # =========================================================================
    # These wrap async methods using a dedicated event loop.
    # Safe to call from sync context (e.g., CocoIndex mutate()).

    def _run_sync(self, coro):
        """Run coroutine synchronously with a fresh event loop."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
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
```

Also add `import asyncio` at the top of the file (after line 6).

### Step 1.4: Run test to verify it passes

```bash
uv run pytest tests/unit/ingestion/test_state_manager_sync.py -v
```

Expected: 2 passed

### Step 1.5: Commit

```bash
git add src/ingestion/unified/state_manager.py tests/unit/ingestion/test_state_manager_sync.py
git commit -m "feat(ingestion): add sync methods to UnifiedStateManager

- _run_sync() helper for fresh event loop
- get_state_sync, should_process_sync
- mark_processing_sync, mark_indexed_sync, mark_error_sync
- mark_deleted_sync, add_to_dlq_sync

Enables sync execution in CocoIndex target connector."
```

---

## Task 2: Add DoclingClient Sync Method

**Files:**
- Modify: `src/ingestion/docling_client.py`
- Test: `tests/unit/ingestion/test_docling_client.py` (update)

### Step 2.1: Write the failing test

Add to `tests/unit/ingestion/test_docling_client.py`:

```python
class TestDoclingClientSync:
    """Tests for sync methods."""

    def test_chunk_file_sync_exists(self):
        """chunk_file_sync() method should exist."""
        from src.ingestion.docling_client import DoclingClient

        assert hasattr(DoclingClient, "chunk_file_sync")

    def test_chunk_file_sync_is_not_coroutine(self):
        """chunk_file_sync() should be sync."""
        import asyncio

        from src.ingestion.docling_client import DoclingClient

        assert not asyncio.iscoroutinefunction(DoclingClient.chunk_file_sync)
```

### Step 2.2: Run test to verify it fails

```bash
uv run pytest tests/unit/ingestion/test_docling_client.py::TestDoclingClientSync -v
```

Expected: FAIL with `AttributeError`

### Step 2.3: Implement chunk_file_sync

Add to `src/ingestion/docling_client.py` after `chunk_file()` method (around line 250):

```python
    def chunk_file_sync(
        self,
        file_path: Path,
        contextualize: bool = True,
    ) -> list[DoclingChunk]:
        """Sync version of chunk_file() for CocoIndex target.

        Creates a fresh event loop to run the async method.
        Safe to call from sync context.

        Args:
            file_path: Path to document file
            contextualize: Whether to add hierarchical context to chunks

        Returns:
            List of DoclingChunk with rich metadata
        """
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # Connect if needed
            if self._client is None:
                loop.run_until_complete(self.connect())
            return loop.run_until_complete(self.chunk_file(file_path, contextualize))
        finally:
            loop.close()
```

### Step 2.4: Run test to verify it passes

```bash
uv run pytest tests/unit/ingestion/test_docling_client.py::TestDoclingClientSync -v
```

Expected: 2 passed

### Step 2.5: Commit

```bash
git add src/ingestion/docling_client.py tests/unit/ingestion/test_docling_client.py
git commit -m "feat(docling): add chunk_file_sync() for sync execution

Creates fresh event loop to run async chunk_file().
Enables use in CocoIndex target connector."
```

---

## Task 3: Refactor Target Connector to Pure Sync

**Files:**
- Modify: `src/ingestion/unified/targets/qdrant_hybrid_target.py`
- Test: `tests/unit/ingestion/test_target_sync_execution.py` (existing)

### Step 3.1: Verify current test failure

```bash
uv run pytest tests/unit/ingestion/test_target_sync_execution.py -v
```

Expected: 2 FAILED (test_mutate_does_not_call_asyncio_run, test_handle_methods_are_sync)

### Step 3.2: Refactor mutate() and handlers

Replace `src/ingestion/unified/targets/qdrant_hybrid_target.py` from line 176 to end:

```python
    @staticmethod
    def mutate(
        *all_mutations: tuple[QdrantHybridTargetSpec, dict[str, QdrantHybridTargetValues | None]],
    ) -> None:
        """Apply data mutations to Qdrant (fully synchronous).

        For each file_id:
        - None value: delete all points for file_id
        - Non-None value: parse, embed, upsert (replace semantics)

        All operations use sync methods to avoid event loop conflicts.
        """
        for spec, mutations in all_mutations:
            for file_id, mutation in mutations.items():
                try:
                    if mutation is None:
                        QdrantHybridTargetConnector._handle_delete(spec, file_id)
                    else:
                        QdrantHybridTargetConnector._handle_upsert(spec, file_id, mutation)
                except Exception as e:
                    logger.error(f"Mutation failed for {file_id}: {e}", exc_info=True)

    @classmethod
    def _handle_delete(cls, spec: QdrantHybridTargetSpec, file_id: str) -> None:
        """Handle file deletion (sync)."""
        writer = cls._get_writer(spec)
        state_manager = cls._get_state_manager(spec)

        writer.delete_file_sync(file_id, spec.collection_name)
        state_manager.mark_deleted_sync(file_id)
        logger.info(f"Deleted: file_id={file_id}")

    @classmethod
    def _handle_upsert(
        cls,
        spec: QdrantHybridTargetSpec,
        file_id: str,
        mutation: QdrantHybridTargetValues,
    ) -> None:
        """Handle file insert/update (sync)."""
        writer = cls._get_writer(spec)
        docling = cls._get_docling(spec)
        state_manager = cls._get_state_manager(spec)

        abs_path = Path(mutation.abs_path)
        source_path = mutation.source_path

        # Compute content hash
        content_hash = compute_content_hash(abs_path)

        # Check if processing needed (skip unchanged)
        if not state_manager.should_process_sync(file_id, content_hash):
            logger.debug(f"Skipping unchanged: {source_path}")
            return

        # Mark processing
        state_manager.mark_processing_sync(file_id)

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

            raise
```

Also remove `import asyncio` from top of file (line 11) since it's no longer used.

### Step 3.3: Run tests to verify they pass

```bash
uv run pytest tests/unit/ingestion/test_target_sync_execution.py -v
```

Expected: 3 passed

### Step 3.4: Run all ingestion tests

```bash
uv run pytest tests/unit/ingestion/ -v
```

Expected: All pass (including test_payload_contract.py, test_cocoindex_init.py)

### Step 3.5: Commit

```bash
git add src/ingestion/unified/targets/qdrant_hybrid_target.py
git commit -m "fix(ingestion): refactor target connector to pure sync execution

- Remove asyncio.run() from mutate()
- Make _handle_delete() and _handle_upsert() sync
- Use *_sync() methods from StateManager, DoclingClient, Writer

Fixes test_target_sync_execution.py failures."
```

---

## Task 4: End-to-End Validation

**Files:**
- None (validation only)

### Step 4.1: Ensure Docker services are running

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "postgres|qdrant|docling"
```

Expected: All 3 services Up

If not:
```bash
make docker-core-up
```

### Step 4.2: Run ingestion once

```bash
. .env && uv run python -m src.ingestion.unified.cli run
```

Expected output: Files processed, chunks indexed

### Step 4.3: Check ingestion status

```bash
. .env && uv run python -m src.ingestion.unified.cli status
```

Expected:
```
=== Ingestion Status ===
  indexed: N (100.0%)
  TOTAL: N

  DLQ: 0 items
```

### Step 4.4: Verify Qdrant data

```bash
curl -s localhost:6333/collections/gdrive_documents_scalar | jq '.result.points_count'
```

Expected: Number > 0

### Step 4.5: Verify payload contract

```bash
curl -s localhost:6333/collections/gdrive_documents_scalar/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit": 1, "with_payload": true}' | jq '.result.points[0].payload | keys'
```

Expected: `["file_id", "metadata", "page_content"]`

### Step 4.6: Commit verification success

```bash
git add -A
git commit -m "test(ingestion): verify end-to-end pipeline execution

- All unit tests pass
- Pipeline processes files from ~/drive-sync/
- Qdrant collection has points with correct payload
- Status command shows indexed files"
```

---

## Task 5: Run Integration Test (Optional)

### Step 5.1: Run E2E test

```bash
RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion_e2e.py -v
```

Expected: All tests pass

---

## Verification Checklist

- [ ] `pytest tests/unit/ingestion/test_state_manager_sync.py` — 2 passed
- [ ] `pytest tests/unit/ingestion/test_docling_client.py::TestDoclingClientSync` — 2 passed
- [ ] `pytest tests/unit/ingestion/test_target_sync_execution.py` — 3 passed
- [ ] `pytest tests/unit/ingestion/` — all pass
- [ ] `make ingest-unified` — files processed
- [ ] `make ingest-unified-status` — shows indexed > 0
- [ ] Qdrant has points with `page_content`, `metadata.file_id`, `metadata.doc_id`

---

## Summary

| Task | Files | Effort |
|------|-------|--------|
| 1. StateManager sync | state_manager.py, new test | 10 min |
| 2. DoclingClient sync | docling_client.py, update test | 5 min |
| 3. Target refactor | qdrant_hybrid_target.py | 15 min |
| 4. E2E validation | none | 10 min |
| **Total** | | **~40 min** |
