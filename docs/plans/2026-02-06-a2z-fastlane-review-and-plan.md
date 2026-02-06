# ТЗ + A→Я Review: RAG Pipeline (Fast-Lane)

Дата: 2026-02-06
Контур: `/opt/rag-fresh` + runtime `vps-*` containers
База сравнения: ТЗ `v2.1` (Fast-Lane Semantic Cache)

## 1) Executive summary

- Инфраструктура в целом поднята (`vps-*` mostly healthy), `ingestion preflight/bootstrap` рабочие.
- Главная проблема сейчас: **runtime дрейфует от текущего кода/compose**. Из-за этого часть Fast-Lane уже есть в исходниках, но **не работает в запущенном боте**.
- По ТЗ v2.1 выполнено частично: core идеи реализованы в source, но не доведены до production runtime и не закрыты эксплуатационные риски.

## 2) Проверка планов за вчера/сегодня

### 2.1 Вчерашние чеклисты (2026-02-05)

- `docs/plans/2026-02-05-vps-deployment-plan.md`: `44 total / 24 done / 20 open`
- `docs/plans/2026-02-05-vps-phase2-plan.md`: `31 total / 6 done / 25 open`

Вывод: нельзя считать, что все планы за вчера внедрены полностью.

### 2.2 Сегодняшние планы (2026-02-06)

- `docs/plans/2026-02-06-orchestrator-review-gap-tz.md` частично устарел по части `bootstrap/preflight`:
  - факт в runtime: `preflight` = `5/5 READY`, `bootstrap` = `collection exists` (OK).

## 3) Статус по твоему ТЗ Fast-Lane v2.1

| Пункт ТЗ | Source (/opt) | Runtime (containers) | Статус |
|---|---|---|---|
| Phase 0: stage-метрики | Есть в source (`PipelineMetrics`, stage timers/counters/observations) | Не применяется в running bot (старый код в контейнере) | `partial` |
| 1.1 `acheck(vector=)` + `astore(vector=)` | Есть в source (`telegram_bot/services/cache.py`) | В `vps-bot` всё ещё prompt-based `acheck/astore` | `partial` |
| 1.2 timeout на cache-check | Есть в source (`timeout=0.3`) | В runtime не применён (старый код) | `partial` |
| 1.3 изоляция по `user_id` | Есть в source (`check/store` с `user_id`) | В runtime не применён (старый код) | `partial` |
| 1.4 fire-and-forget store | Есть в source (`create_task`) | В runtime не применён (старый код) | `partial` |
| 1.5 отключить/починить Langfuse | В source есть graceful disable через `telegram_bot/observability.py` | В runtime остаются warning (старый код) | `partial` |
| 1.5 `uvloop` | Зависимость добавлена в `pyproject.toml` | Не активирован в runtime entrypoint | `partial` |
| Phase 2 threshold tuning | `set_threshold()` есть в source | Операционно не внедрено в runtime | `partial` |
| Phase 2 нормализация RU/UK | Есть в source (`normalize_ru_uk`) | В runtime не применена (старый код) | `partial` |
| Phase 2 TTL стратегия по типам контента | Частично: pattern-based TTL в source (`get_ttl_for_query`) | В runtime не применено (старый код) | `partial` |
| Phase 3 ONNX BGE-M3 | Нет | Нет | `open` |

## 4) Findings (A→Я) — только актуальные

### CRITICAL

1. Runtime drift: контейнеры не соответствуют текущему compose/source.
   - В текущем compose нет сервиса `bm42`, но `vps-bm42` продолжает работать (orphan).
   - `vps-ingestion` всё ещё с code bind-mount (`/app/src`, `/app/telegram_bot`), хотя в текущем compose описан только `/data/drive-sync`.
   - Хэши `bot.py/cache.py/vectorizers.py` в `/app/...` отличаются от `/opt/rag-fresh/...`.

2. Fast-Lane не в production runtime.
   - В running `vps-bot` используется старый путь `acheck(prompt=...)`/`astore(prompt=...)` без `vector=` и без timeout guard.
   - Следствие: лишняя latency на semantic cache и нестабильная задержка ответов.

### HIGH

1. Manifest identity логически расходится с заявленной целью rename-stability.
   - В `flow.py` заявлено: rename/move не меняет `file_id` при том же контенте (`src/ingestion/unified/flow.py:68`).
   - Реализация `GDriveManifest` использует ключ `path:content_hash`, поэтому при rename создаётся новый ID (`src/ingestion/unified/manifest.py:72`).
   - Проверка через `uv run python` подтверждает разные ID для одинакового hash и разных путей.

2. Qdrant collection schema не соответствует ожиданию по ColBERT.
   - Bootstrap-скрипты описывают `dense+colbert+bm42`:
     - `src/ingestion/unified/cli.py:219`
     - `scripts/setup_qdrant_collection.py:102`
   - Фактическая коллекция `gdrive_documents_bge`: `dense + sparse(bm42)` без `colbert` (runtime check).

3. LiteLLM в runtime на RC image, не на stable.
   - `docker-compose.vps.yml:166`

4. BGE cache vectorizer fallback имеет несовместимость response schema.
   - `BgeM3CacheVectorizer` читает `data["embeddings"]` (`telegram_bot/services/vectorizers.py:209`),
   - тогда как основной BGE клиент использует `dense_vecs` (`telegram_bot/services/bge_m3_dense.py:62`).
   - При fallback path возможны `KeyError`/cache miss cascade.

5. Bot preflight не fail-fast.
   - При недоступности зависимостей бот продолжает старт с warning (`telegram_bot/bot.py:878`), что усложняет эксплуатацию и может приводить к деградации в runtime.

### MEDIUM

1. Технический нейминг-долг: sparse cache ключи и часть меток всё ещё с `bm42`, хотя sparse уже через BGE-M3.
   - `telegram_bot/services/cache.py:520`
   - `telegram_bot/services/cache.py:563`
   - `telegram_bot/bot.py:325`

2. Операционный дрейф между каталогами `/opt/rag-fresh` и `/home/admin/rag-fresh` остаётся риском ошибок деплоя.

## 5) Что уже подтверждено как рабочее

- `ingestion preflight`: `5/5 READY`.
- `ingestion bootstrap`: idempotent, отрабатывает.
- Qdrant доступен, коллекция `gdrive_documents_bge` существует, points > 0.
- Redis доступен, базовые cache-prefix операции живые.

## 6) Active backlog (только невыполненное)

### P0 (сначала)

- [ ] P0-1: Убрать runtime drift.
  - Рекреейт `bot/ingestion` из `/opt/rag-fresh` и удалить orphan `vps-bm42`.
  - Добиться совпадения checksum `/opt/...` == `/app/...`.
  - DoD: `docker compose config --services` и `docker ps` консистентны; лишних сервисов нет.

- [ ] P0-2: Довести Fast-Lane до runtime.
  - В runtime должны быть: `acheck(vector=...)`, timeout guard, `astore(vector=...)`, user isolation по `user_id`, RU/UK normalizer и stage-метрики.
  - DoD: в логах cached path без analyzer/search/rerank/llm.

- [ ] P0-3: Исправить identity алгоритм manifest для rename/move.
  - Убрать зависимость `file_id` от пути (`path:content_hash`) и внедрить стратегию `Drive ID first` (или другой стабильный identity key), content-hash оставить как fallback/версионирование.
  - DoD: rename/move файла не создаёт новый `file_id` и не дублирует чанки в Qdrant.

- [ ] P0-4: Правильный Docker reconcile/rebuild (без ручных рассинхронов).
  - Использовать единый путь `/opt/rag-fresh`.
  - Выполнить controlled recreate:
    - `docker compose -f docker-compose.vps.yml down --remove-orphans`
    - `docker compose -f docker-compose.vps.yml up -d --build --pull missing --force-recreate --remove-orphans`
  - DoD: orphan-сервисов нет (`vps-bm42` удален), runtime соответствует текущему compose/source.

### P1

- [ ] P1-1: Langfuse hardening.
  - Если ключей нет: полностью disable без warning-spam.
  - DoD: нет повторяющихся auth/context warning в bot logs.

- [ ] P1-2: LiteLLM stable rollout.
  - Перевести на stable tag, проверить health и fallback chain.
  - DoD: runtime image = запланированный stable.

- [ ] P1-3: ColBERT policy.
  - Выбрать один путь:
  - A) официально выключаем ColBERT в ТЗ и коде;
  - B) вводим новую коллекцию со схемой `colbert` + план переиндексации.
  - DoD: схема коллекции и rerank-стратегия не противоречат друг другу.

- [ ] P1-4: Baseline latency metrics (Phase 0 из ТЗ).
  - Собирать p50/p95: `embed_dense`, `cache_acheck`, `qdrant_search`, `rerank`, `llm_generate`, `total`.
  - DoD: есть минимум 24h baseline для решений Phase 2/3.

- [ ] P1-5: Docker cleanup policy (без потери рабочих данных).
  - Внедрить регулярную чистку только безопасных объектов:
    - build cache: `docker builder prune -f --filter 'until=168h'`
    - dangling/unused images: `docker image prune -f`
  - Volumes чистить только по allowlist и только когда проверено, что volume не используется.
  - DoD: предсказуемое использование диска, cleanup не ломает persistent data (`qdrant_data`, `postgres_data`, `redis_data`).

- [ ] P1-6: Унифицировать контракт BGE `/encode/dense` в vectorizer fallback.
  - Поддержать оба ключа ответа (`dense_vecs` и `embeddings`) либо привести все клиенты к единому контракту.
  - DoD: fallback vectorizer path не падает на schema mismatch.

- [ ] P1-7: Определить политику preflight на старте бота (fail-fast vs degrade).
  - Для критичных зависимостей (`qdrant`, `redis`, `litellm`, `bge-m3`) зафиксировать поведение и алерты.
  - DoD: предсказуемый startup-behavior при деградации инфраструктуры.

### P2

- [ ] P2-1: Cache quality tuning (threshold/TTL/FP control).
- [ ] P2-2: RU/UK query normalization перед embed.
- [ ] P2-3: ONNX BGE-M3 отдельным rollout-планом после стабилизации runtime.

## 7) Порядок исполнения (обязательный)

1. P0-1 Runtime drift
2. P0-2 Fast-Lane runtime
3. P0-3 Manifest identity fix
4. P0-4 Docker reconcile/rebuild
5. P1-1 Langfuse
6. P1-2 LiteLLM stable
7. P1-3 ColBERT policy
8. P1-4 Метрики baseline
9. P1-5 Docker cleanup policy
10. P1-6 BGE vectorizer fallback contract
11. P1-7 Bot preflight policy
12. P2 этапы

## 8) Runbook: Rebuild + Cleanup

### 8.1 Pre-check

```bash
cd /opt/rag-fresh
docker compose -f docker-compose.vps.yml config --services
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

### 8.2 Reconcile + rebuild (источник правды: текущий compose)

```bash
cd /opt/rag-fresh
docker compose -f docker-compose.vps.yml down --remove-orphans
docker compose -f docker-compose.vps.yml up -d --build --pull missing --force-recreate --remove-orphans
docker compose -f docker-compose.vps.yml --profile ingest up -d --build --force-recreate ingestion
```

### 8.3 Post-check

```bash
cd /opt/rag-fresh
docker compose -f docker-compose.vps.yml ps
docker compose -f docker-compose.vps.yml --profile ingest exec -T ingestion uv run python -m src.ingestion.unified.cli preflight
docker compose -f docker-compose.vps.yml --profile ingest exec -T ingestion uv run python -m src.ingestion.unified.cli bootstrap
docker inspect vps-ingestion --format '{{range .Mounts}}{{println .Destination " | " .Source}}{{end}}'
```

Ожидание:
- orphan-контейнеров нет;
- только сервисы из `docker compose config --services`;
- `preflight` и `bootstrap` без ошибок.

### 8.4 Safe cleanup (после стабилизации)

```bash
docker builder prune -f --filter 'until=168h'
docker image prune -f
```

Опционально (только при подтвержденной безопасности):

```bash
docker volume prune -f
```

Внимание: volume prune не запускать без проверки, что данные в named volumes не нужны.

## 9) Контрольные команды ревью (использованы)

```bash
cd /opt/rag-fresh
docker compose -f docker-compose.vps.yml ps --format json
docker compose -f docker-compose.vps.yml --profile ingest exec -T ingestion uv run python -m src.ingestion.unified.cli preflight
docker compose -f docker-compose.vps.yml --profile ingest exec -T ingestion uv run python -m src.ingestion.unified.cli bootstrap
docker inspect vps-ingestion --format '{{range .Mounts}}{{println .Destination " | " .Source}}{{end}}'
docker compose -f docker-compose.vps.yml config --services
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

## 10) Важное ограничение текущего цикла

- В этом цикле выполнен именно **review + ТЗ**, без внедрения фиксов и без полного прогона тестов.

## 11) Источники (Context7 + CLI)

- Context7 `/docker/docs`: базовые практики `docker compose build/up`, `docker system/image/volume prune`.
- Context7 `/docker/compose`: поведение `docker compose up` при изменении конфигурации/образов.
- Локальная проверка CLI:
  - `docker compose up --help` (флаги `--force-recreate`, `--remove-orphans`, `--build`, `--pull`)
  - `docker builder prune --help`
  - `docker image prune --help`
  - `docker volume prune --help`
