# Qdrant Snapshots for Backup — Implementation Plan

**Issue:** [#70](https://github.com/yastman/rag/issues/70) feat: Qdrant snapshots for backup before re-indexing
**Priority:** P2 | **Effort:** Low | **Milestone:** Stream-F: Infra-Sec

## Goal

Автоматический snapshot Qdrant коллекций перед re-indexing операциями. Быстрое восстановление при сбое ingestion. Collection cloning для A/B тестирования.

## Текущее состояние

Уже существуют скрипты:

| Файл | Назначение | Статус |
|------|-----------|--------|
| `scripts/qdrant_snapshot.py` | Python-скрипт: create + download snapshot (async, httpx) | Работает, 304 LOC |
| `scripts/qdrant_backup.sh` | Bash: curl-based backup + retention 7 дней | Работает, VPS-ориентирован |
| `scripts/qdrant_restore.sh` | Bash: upload + recover snapshot | Работает, интерактивный |
| `Makefile:qdrant-backup` | `uv run python scripts/qdrant_snapshot.py` | Готов |

**Что отсутствует:**
1. Pre-ingestion hook — snapshot НЕ создаётся перед `make ingest-unified`
2. Scheduled backup — нет cron/systemd timer
3. Collection cloning для A/B — нет утилиты
4. Retention policy в Python-скрипте — нет (только в bash-скрипте)
5. Snapshot cleanup на сервере Qdrant — bash делает DELETE, Python нет
6. Тесты — нет unit/integration тестов

## Qdrant Snapshot API (qdrant-client)

    # AsyncQdrantClient методы:
    await client.create_snapshot(collection_name="col")      # -> SnapshotDescription
    await client.list_snapshots(collection_name="col")       # -> list[SnapshotDescription]
    await client.create_full_snapshot()                       # -> SnapshotDescription (all collections)
    await client.delete_snapshot(collection_name, snapshot_name)
    # SnapshotDescription.name — имя файла (.snapshot)

    # REST API (для download):
    GET /collections/{name}/snapshots/{snapshot_name}

    # Recover (upload + restore):
    POST /collections/{name}/snapshots/upload  (multipart)
    PUT  /collections/{name}/snapshots/{snapshot}/recover

## Шаги реализации

### Шаг 1. Pre-ingestion snapshot hook (5 мин)

**Файл:** `src/ingestion/unified/cli.py` (строки 25-38, функция `cmd_run`)

Добавить вызов snapshot ПЕРЕД запуском ingestion:

    # В cmd_run(), после config = UnifiedConfig(), перед run_once/run_watch:
    from scripts.qdrant_snapshot import run_backup
    from pathlib import Path

    backup_dir = Path(os.getenv("QDRANT_BACKUP_DIR", "/backups"))
    qdrant_url = config.qdrant_url  # или os.getenv("QDRANT_URL")
    exit_code = asyncio.run(run_backup(
        qdrant_url=qdrant_url,
        api_key=os.getenv("QDRANT_API_KEY"),
        collections=[config.collection_name],
        output_dir=backup_dir,
    ))
    if exit_code == 2:
        logger.error("Snapshot failed, aborting ingestion")
        return 1
    elif exit_code == 1:
        logger.warning("Partial snapshot failure, continuing...")

**Альтернатива:** Makefile target `ingest-with-backup`:

    ingest-with-backup: qdrant-backup ingest-unified  ## Snapshot + ingest

Обе опции реализовать. CLI hook — для Docker/VPS, Makefile — для dev.

**Файл:** `Makefile` (строка ~756, после `qdrant-backup`)

    ingest-with-backup: qdrant-backup ingest-unified  ## Snapshot before ingestion

### Шаг 2. Retention policy в Python-скрипте (5 мин)

**Файл:** `scripts/qdrant_snapshot.py` (строки 129-214, функция `run_backup`)

Добавить параметр `--retention-days` (default 7):

    # После успешного download, удалить snapshot с сервера Qdrant:
    await client.delete_snapshot(collection_name=name, snapshot_name=snapshot_info.name)

    # Удалить старые локальные файлы:
    import time
    cutoff = time.time() - (retention_days * 86400)
    for old_file in output_dir.glob("*.snapshot"):
        if old_file.stat().st_mtime < cutoff:
            old_file.unlink()
            logger.info("Deleted old backup: %s", old_file.name)

**Аргумент CLI:** `--retention-days` (default 7)

    parser.add_argument("--retention-days", type=int, default=7,
                        help="Delete local snapshots older than N days")

### Шаг 3. Makefile targets для restore и list (3 мин)

**Файл:** `Makefile` (после `qdrant-backup` target, строка ~756)

    qdrant-list: ## List available Qdrant snapshots
        @echo "$(BLUE)Local snapshots:$(NC)"
        @ls -lh /backups/*.snapshot 2>/dev/null || echo "  No local snapshots"

    qdrant-restore: ## Restore Qdrant from snapshot (BACKUP_FILE=path)
        @test -n "$(BACKUP_FILE)" || (echo "Usage: make qdrant-restore BACKUP_FILE=path"; exit 1)
        bash scripts/qdrant_restore.sh "$(BACKUP_FILE)"

### Шаг 4. Collection cloning для A/B тестирования (5 мин)

**Файл:** `scripts/qdrant_snapshot.py` — добавить subcommand `clone`

Добавить функцию clone:

    async def clone_collection(
        client: AsyncQdrantClient,
        source: str,
        target: str,
        qdrant_url: str,
    ) -> bool:
        # 1. Создать snapshot source коллекции
        snapshot = await client.create_snapshot(collection_name=source)
        # 2. Если target существует — удалить
        collections = await get_all_collections(client)
        if target in collections:
            await client.delete_collection(target)
        # 3. Recover snapshot в target коллекцию
        snapshot_url = f"{qdrant_url}/collections/{source}/snapshots/{snapshot.name}"
        await client.recover_snapshot(
            collection_name=target,
            location=snapshot_url,
        )
        # 4. Удалить snapshot с сервера
        await client.delete_snapshot(collection_name=source, snapshot_name=snapshot.name)
        return True

Использование:

    python scripts/qdrant_snapshot.py clone \
        --source gdrive_documents_bge \
        --target gdrive_documents_bge_experiment

### Шаг 5. Scheduled backup (cron) документация (2 мин)

**Файл:** `scripts/README.md` — добавить секцию "Scheduled Backup"

    # Cron setup (VPS)
    # Ежедневно в 3:00 UTC
    0 3 * * * cd /opt/rag-fresh && python scripts/qdrant_snapshot.py --retention-days 7 >> /var/log/qdrant-backup.log 2>&1

Также добавить systemd timer как альтернативу (описание в README).

**Файл:** `docker-compose.vps.yml` — НЕ добавлять отдельный backup container.
Рекомендация: crontab на хосте VPS, т.к. backup — одноразовая операция.

### Шаг 6. Unit тесты (5 мин)

**Файл:** `tests/unit/test_qdrant_snapshot.py` (новый)

    # Тесты:
    # 1. test_get_all_collections — mock client.get_collections()
    # 2. test_create_and_download_snapshot — mock create_snapshot + httpx
    # 3. test_dry_run — проверить что snapshot НЕ создаётся
    # 4. test_retention_cleanup — создать файлы с mtime > 7 дней, проверить удаление
    # 5. test_clone_collection — mock create_snapshot + recover_snapshot

## Test Strategy

| Тест | Файл | Тип |
|------|------|-----|
| get_all_collections mock | `tests/unit/test_qdrant_snapshot.py` | Unit |
| create+download snapshot mock | `tests/unit/test_qdrant_snapshot.py` | Unit |
| retention cleanup | `tests/unit/test_qdrant_snapshot.py` | Unit |
| clone collection mock | `tests/unit/test_qdrant_snapshot.py` | Unit |
| Pre-ingestion hook | `tests/unit/ingestion/test_cli_snapshot_hook.py` | Unit |
| E2E backup+restore (Qdrant up) | Manual: `make qdrant-backup && make qdrant-restore` | E2E |

## Acceptance Criteria

1. `make qdrant-backup` создаёт snapshot и скачивает .snapshot файл
2. `make ingest-with-backup` создаёт snapshot ПЕРЕД ingestion
3. CLI `--retention-days 7` удаляет старые .snapshot файлы
4. Snapshot удаляется с сервера Qdrant после download (экономия диска)
5. `clone` subcommand клонирует коллекцию через snapshot + recover
6. Unit тесты проходят: `pytest tests/unit/test_qdrant_snapshot.py -v`
7. Документация в `scripts/README.md` обновлена

## Effort Estimate

| Шаг | Время |
|-----|-------|
| 1. Pre-ingestion hook | 5 мин |
| 2. Retention policy | 5 мин |
| 3. Makefile targets | 3 мин |
| 4. Collection cloning | 5 мин |
| 5. Scheduled docs | 2 мин |
| 6. Unit тесты | 5 мин |
| **Итого** | **~25 мин** |

## Риски

| Риск | Митигация |
|------|----------|
| Snapshot большой коллекции (>1GB) занимает время | `httpx.Timeout(300)` уже установлен |
| Диск VPS заполнится | retention_days=7 + delete с сервера |
| Ingestion abort при failed snapshot | Partial failure (exit=1) продолжает, total (exit=2) останавливает |
| Clone перезаписывает существующую коллекцию | Явное предупреждение в CLI, `--force` флаг |
