# Review: статусы "выполнено" в общем плане

Дата: 2026-02-06
План: `docs/plans/2026-02-01-rag-2026-tz.md`
Фокус: ревью задач, помеченных как выполненные (`✅ COMPLETE` / `[x]`), по текущему состоянию кода и рантайма.

## Findings

| ID | Severity | Finding | Evidence | Risk | Recommendation |
|---|---|---|---|---|---|
| REV-01 | Critical | Публичная команда `make ingest-gdrive` ведет в путь, где Google Drive ingestion явно не реализован | `Makefile:670` → `telegram_bot/services/ingestion_cocoindex.py:54` → `src/ingestion/service.py:210`/`src/ingestion/service.py:214` | Операционно выглядит как готовый путь, но фактически нерабочий | Либо перепривязать `ingest-gdrive` на `src.ingestion.gdrive_flow`, либо явно пометить/удалить legacy target |
| REV-02 | High | `Milestone J` отмечен как `✅ COMPLETE`, но раздел J.6 помечен как `N/A` для make-targets при том, что make-targets существуют и один из них сейчас невалиден | `docs/plans/2026-02-01-rag-2026-tz.md:804`, `docs/plans/2026-02-01-rag-2026-tz.md:846`, `Makefile:665`, `Makefile:670` | Ложное ощущение завершенности ingestion-цепочки | Разделить статус на: `CocoIndex watcher path = done`, `legacy make ingest-gdrive = deprecated/fix needed` |
| REV-03 | Medium | В плане отмечено, что прямой `pip install` убран из CI/scripts/docs, но в актуальной документации для разработки еще есть `pip install -e .` | claim: `docs/plans/2026-02-01-rag-2026-tz.md:917`; факт: `docs/LOCAL-DEVELOPMENT.md:101` | Drift между `uv-first` политикой и инструкциями для команды | Обновить `docs/LOCAL-DEVELOPMENT.md` на `uv sync`/`uv run` |
| REV-04 | Medium | Документация Milestone J ссылается на внешний путь `~/.claude/CLAUDE.md`, не версионируемый в репозитории | `docs/plans/2026-02-01-rag-2026-tz.md:869` | Проверяемость и воспроизводимость статуса снижаются | Перенести/дублировать ключевую ingestion-документацию в `docs/` внутри репозитория |

## Verified As Completed

- ACORN статус обновлен корректно: блокировка снята, `AcornSearchParams` доступен в текущем SDK (`qdrant-client 1.16.2`) и отражен в плане.
  refs: `docs/plans/2026-02-01-rag-2026-tz.md:623`, `requirements.txt:4`, `src/retrieval/search_engines.py:16`
- Docker и CI действительно переведены на `uv`-ориентированный путь.
  refs: `Dockerfile:1`, `Dockerfile:5`, `.github/workflows/ci.yml:17`, `.github/workflows/ci.yml:68`
- Redis `maxmemory-samples=10` зафиксирован в compose и в текущем runtime VPS.
  refs: `docker-compose.vps.yml:42`, runtime check `docker exec vps-redis redis-cli CONFIG GET maxmemory-samples` -> `10`
- Коллекция VPS `gdrive_documents_bge` существует и содержит данные.
  runtime: `GET http://qdrant:6333/collections/gdrive_documents_bge` -> `points_count=278`

## Open Questions

1. `make ingest-gdrive` должен жить как user-facing команда или считается legacy после перехода на `vps-ingestion + rclone`?
2. Нужен ли отдельный документ `docs/DOCUMENT-INGESTION.md` как source of truth для Milestone J, чтобы убрать зависимость от внешнего `~/.claude/CLAUDE.md`?
