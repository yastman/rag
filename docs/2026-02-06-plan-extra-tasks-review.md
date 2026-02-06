# Review: статусы "выполнено" в общем плане

Дата: 2026-02-06
План: `docs/plans/2026-02-01-rag-2026-tz.md`
Фокус: ревью задач, помеченных как выполненные (`✅ COMPLETE` / `[x]`), по текущему состоянию кода и рантайма.

## Findings — All Resolved

| ID | Severity | Finding | Fix | Status |
|---|---|---|---|---|
| REV-01 | Critical | `make ingest-gdrive` вёл в нереализованный путь | `Makefile`: target помечен `[DEPRECATED]`, выводит сообщение с рабочими альтернативами (`ingest-gdrive-run`, `ingest-gdrive-watch`) | ✅ Fixed |
| REV-02 | High | J.6 помечен как `N/A` при наличии реальных make-targets | `docs/plans/2026-02-01-rag-2026-tz.md`: J.6 обновлён — перечислены реальные targets, legacy `ingest-gdrive` отмечен deprecated | ✅ Fixed |
| REV-03 | Medium | `docs/LOCAL-DEVELOPMENT.md` содержал `pip install -e .` | Заменено на `uv sync` / `uv run` (uv-first стандарт) | ✅ Fixed |
| REV-04 | Medium | J.10 ссылался на `~/.claude/CLAUDE.md` (вне репо) | Заменено на ссылки к `docker-compose.vps.yml`, `src/ingestion/`, `docs/plans/2026-02-05-vps-phase2-plan.md` | ✅ Fixed |

## Verified As Completed

- ACORN статус обновлен корректно: блокировка снята, `AcornSearchParams` доступен в текущем SDK (`qdrant-client 1.16.2`) и отражен в плане.
  refs: `docs/plans/2026-02-01-rag-2026-tz.md:623`, `requirements.txt:4`, `src/retrieval/search_engines.py:16`
- Docker и CI действительно переведены на `uv`-ориентированный путь.
  refs: `Dockerfile:1`, `Dockerfile:5`, `.github/workflows/ci.yml:17`, `.github/workflows/ci.yml:68`
- Redis `maxmemory-samples=10` зафиксирован в compose и в текущем runtime VPS.
  refs: `docker-compose.vps.yml:42`, runtime check `docker exec vps-redis redis-cli CONFIG GET maxmemory-samples` -> `10`
- Коллекция VPS `gdrive_documents_bge` существует и содержит данные.
  runtime: `GET http://qdrant:6333/collections/gdrive_documents_bge` -> `points_count=278`

## Resolved Questions

1. **`make ingest-gdrive`** — помечен как deprecated. Рабочие команды: `make ingest-gdrive-run` (однократный запуск) и `make ingest-gdrive-watch` (watch mode). Production — через `docker compose` (vps-ingestion).
2. **Ingestion docs** — ключевая документация теперь ссылается на внутренние файлы репозитория (`docker-compose.vps.yml`, `src/ingestion/`, `docs/plans/2026-02-05-vps-phase2-plan.md`), не на внешний `~/.claude/CLAUDE.md`.
