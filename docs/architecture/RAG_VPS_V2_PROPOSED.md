# RAG VPS — целевая спецификация reusable Python RAG-монолита

**Дата:** 29 августа 2026 года<br>
**Репозиторий:** `yastman/genesis-rag-api`<br>
**Целевая ветка:** `dev`<br>
**Назначение:** небольшая production-ready RAG-«рабочая лошадка», которую можно разворачивать как отдельный сервис в разных проектах без копирования бизнес-логики и без тяжёлого фреймворк-стека.

---

## 1. Итоговое решение

Целевой продукт — **модульный монолит** в следующем смысле:

- один GitHub-репозиторий;
- один Python-пакет;
- один lockfile;
- один Dockerfile и один Docker-образ;
- один набор доменных модулей;
- два запускаемых процесса из одного образа:
  - `rag-api` — HTTP/Python/Telegram request path;
  - `rag-worker` — тяжёлый и восстанавливаемый indexing/publication path;
- одна PostgreSQL;
- один Qdrant OSS;
- один локальный content-addressed volume для оригиналов;
- Valkey/Redis только как отключённый по умолчанию exact cache;
- DeepEval только как offline evaluation tooling.

Это **не микросервисы**: API и worker не имеют отдельных репозиториев, моделей данных или HTTP-контрактов между собой. Они используют один пакет и координируются через одну PostgreSQL. Разделение процессов нужно только для изоляции тяжёлых Docling/embedding/Qdrant операций от latency пользовательских ответов.

```text
                     Python / REST / Telegram
                              │
                              ▼
                    ┌───────────────────┐
                    │      rag-api      │
                    │ thin adapters     │
                    └─────────┬─────────┘
                              │
                    public RagApplication API
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
       PostgreSQL       Qdrant alias      Model SDKs
       ledger/queue     read path         OpenRouter
             ▲                ▲
             │                │
                    ┌─────────┴─────────┐
                    │    rag-worker     │
                    │ build / validate  │
                    │ publish / recover │
                    └─────────┬─────────┘
                              │
                              ▼
                  content-addressed originals

Optional:
  Valkey exact answer cache

Offline only:
  deterministic evaluation + DeepEval/Codex
```

---

## 2. Почему текущую основу нельзя переписывать

В живом `genesis-rag-api` уже реализованы наиболее сложные и полезные части production RAG:

- exact Git/manifest source verification;
- canonical `document_id` и deterministic point identities;
- Docling heading-aware chunking;
- Qwen3 dense embeddings;
- Qdrant filtered retrieval;
- Cohere reranking;
- native structured generation;
- opaque evidence IDs;
- server-owned citations;
- immutable physical Qdrant collections;
- exact Count/Scroll reconciliation;
- atomic alias switching;
- deterministic Recall/Precision/MRR/nDCG;
- private Gold dataset;
- DeepEval/Codex evaluation, fingerprinting, variance и human calibration.

Новый этап не строит ещё один RAG pipeline. Он добавляет недостающий source-neutral document lifecycle, durable publication execution и тонкий HTTP product surface вокруг уже проверенного ядра.

---

## 3. Принципы, которые нельзя нарушать

### 3.1 Один owner на каждый вид данных

```text
Original/source bytes       → authoritative
PostgreSQL ledger           → authoritative
Qdrant vectors/chunks       → derived, rebuildable
Valkey cache                → disposable
Evaluation artifacts        → evidence, not runtime truth
Model output                → untrusted until validated
```

Удаление Qdrant volume не должно приводить к потере документа или невозможности восстановить логически идентичный индекс.

### 3.2 Native SDK first

Использовать напрямую:

- OpenRouter SDK;
- `qdrant-client`;
- Docling public APIs;
- Pydantic;
- Psycopg 3;
- FastAPI;
- optional `redis` asyncio client для Valkey-compatible cache.

Не добавлять LangChain, LlamaIndex, LangGraph, Haystack, LiteLLM Proxy, DI container, service locator, provider registry или vector-store registry, пока не появится второй реальный implementation и измеренная необходимость.

### 3.3 Не создавать интерфейс ради теста

Публичными являются только реально необходимые application contracts:

- `DocumentSnapshot`;
- `CorpusSnapshot`;
- `Evidence`;
- `Citation`;
- `GroundedAnswer`;
- `RagExecution`;
- `RagApplication`;
- `execute()`;
- `ask()`.

Не вводить абстрактные `BaseRetriever`, `BaseVectorStore`, `Provider`, `RepositoryFactory`, `PipelineRegistry` и аналогичные оболочки.

### 3.4 Один deployment — один security clearance

V1 не является multi-tenant SaaS. Один экземпляр сервиса обслуживает один проект/контур доступа. `corpus_id` остаётся domain identity, но не выдаётся за ACL или tenant isolation.

Для другого клиента или уровня доступа разворачивается отдельный экземпляр Compose. RBAC, OAuth, SSO и document ACL — отдельный будущий продуктовый срез.

### 3.5 Markdown-only v1

Первый reusable contract принимает UTF-8 Markdown. PDF/DOCX/OCR не входят в базовую поставку. Они должны добавляться позднее как отдельные parser extras после определения требований и evaluation.

Это сохраняет маленький dependency surface и уже проверенную семантику Genesis.

---

## 4. Что остаётся без изменения

Production retrieval baseline:

```text
question
  → Qwen3 query embedding
  → Qdrant dense retrieval, top 20
  → strict payload/evidence validation
  → Cohere Rerank 4
  → score threshold
  → grounded structured completion
  → validated evidence selection
  → server-built citations or refusal
```

На этапе lifecycle migration запрещено одновременно менять:

- embedding model;
- dimensions;
- chunk size;
- chunker;
- retrieval `top_k`;
- reranker;
- rerank threshold;
- prompt;
- completion model;
- dense search на hybrid search.

Каждая из этих переменных меняется только отдельным bounded experiment на frozen corpus/Gold.

---

## 5. Целевая структура Python-пакета

Сохранить плоскую и понятную структуру. Не вводить каталоги `domain/application/infrastructure/adapters/repositories/usecases`, если один файл с прямым owner решает задачу.

```text
src/rag/
  __init__.py
  application.py       # RagApplication composition root
  settings.py

  documents.py         # snapshots, document/revision identities
  originals.py         # content-addressed original store
  ledger.py            # direct Psycopg SQL ownership
  migrations.py        # tiny forward-only SQL migration runner
  publication.py       # freeze/build/validate/activate/recover state machine
  worker.py            # PostgreSQL claim loop, no domain logic duplication

  ingest.py            # retained Docling preparation/chunking primitives
  chunk_record.py      # payload schema and deterministic point identities
  qdrant.py            # native Qdrant operations

  answer.py            # execute/ask, evidence, answer contract
  qwen_embeddings.py
  cohere_rerank.py
  openrouter.py

  git_source.py        # Genesis-specific source adapter
  manifest.py          # Genesis-specific manifest governance

  http_api.py          # thin FastAPI routes and wire models
  cli.py
  bot.py               # optional Telegram adapter
  diagnostics.py

migrations/
  0001_initial.sql
  0002_....sql

evaluation/
  ...                  # existing offline evaluation package
```

Правила:

- `http_api.py`, `cli.py`, `bot.py` не содержат retrieval/indexing logic;
- `worker.py` не содержит Qdrant/domain logic, а только claim/loop;
- `ledger.py` не знает FastAPI;
- `publication.py` не знает HTTP;
- production modules никогда не импортируют `evaluation`;
- не дробить существующий файл только ради архитектурной симметрии;
- рефакторить крупный файл только когда новая ответственность действительно требует отдельного owner.

---

## 6. Source-neutral document contracts

```python
@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    document_id: str
    source_key: str
    source_version: str | None
    content_sha256: str
    media_type: str
    size_bytes: int
    storage_key: str


@dataclass(frozen=True, slots=True)
class CorpusSnapshot:
    corpus_id: str
    documents: tuple[DocumentSnapshot, ...]
    manifest_sha256: str
```

### Значение полей

- `document_id` — постоянная бизнес-идентичность документа;
- `source_key` — внешний locator/provenance, но не identity;
- `source_version` — revision/ETag/commit, если источник его предоставляет;
- `content_sha256` — SHA-256 исходных bytes;
- `storage_key` — путь внутри content-addressed store;
- `manifest_sha256` — digest exact desired set активных document revisions.

Core не должен знать, пришёл snapshot из:

- Git;
- HTTP upload;
- filesystem;
- SharePoint;
- Google Drive;
- S3.

Genesis Git adapter сохраняет все текущие строгие проверки и лишь преобразует проверенные bytes в generic snapshot.

---

## 7. Content-addressed originals

Физическая структура:

```text
/data/originals/sha256/ab/<full-sha256>
```

### Write contract

```text
bounded input stream
  → unique temporary file in the same filesystem
  → SHA-256 while streaming
  → enforce byte ceiling
  → flush + fsync(file)
  → verify size/digest
  → atomic rename to digest path
  → fsync(parent directory)
```

Требования:

- пользовательское имя файла никогда не становится filesystem path;
- запрещён path traversal;
- temp file имеет непредсказуемое имя и права `0600`;
- incomplete file никогда не видим как original;
- существующий digest-path проверяется, а не молча доверяется;
- чтение original может fail-closed при digest mismatch;
- identical bytes физически хранятся один раз;
- logical delete не удаляет original;
- GC originals не входит в первый production slice и добавляется отдельной destructive operation с dry-run.

PostgreSQL не хранит document BLOB.

---

## 8. PostgreSQL как тонкий control plane

Использовать PostgreSQL только там, где нужна транзакционность и durable lifecycle.

Не хранить в PostgreSQL:

- chunk text;
- embeddings;
- Qdrant points;
- evaluation text;
- cache entries;
- original BLOB.

Использовать direct Psycopg 3 и `psycopg_pool.AsyncConnectionPool`. Не использовать SQLAlchemy ORM и Alembic.

### 8.1 `schema_migrations`

```text
version       integer primary key
sha256        text not null
applied_at    timestamptz not null
```

Migrations — forward-only numbered SQL files. Маленький runner:

- берёт PostgreSQL advisory lock;
- проверяет digest уже применённых migrations;
- применяет новые по порядку;
- никогда не генерирует SQL автоматически;
- отказывается запускаться при modified applied migration.

### 8.2 `corpora`

```text
id                     text primary key
active_publication_id  uuid null
created_at             timestamptz not null
updated_at             timestamptz not null
```

V1 содержит один configured corpus row, но схема не привязывает identity к имени Qdrant alias.

### 8.3 `documents`

```text
id                   uuid primary key
document_id          text not null unique
desired_revision_id  uuid null
source_key            text not null
last_source_version   text null
deleted_at            timestamptz null
created_at            timestamptz not null
updated_at            timestamptz not null
```

`document_id` — стабильный ID. Rename/change `source_key` не меняет его.

### 8.4 `document_revisions`

```text
id               uuid primary key
document_fk      uuid not null references documents(id)
content_sha256   text not null
storage_key      text not null
media_type       text not null
size_bytes       bigint not null
source_version   text null
created_at       timestamptz not null

unique(document_fk, content_sha256)
```

Revision immutable. Повторная загрузка тех же bytes — NOOP. Изменённые bytes создают новую revision. Старые revisions не удаляются.

### 8.5 `publications`

```text
id                         uuid primary key
corpus_id                  text not null
corpus_manifest_sha256     text not null
index_pipeline_fingerprint text not null
index_revision             text not null
physical_collection        text not null
point_manifest_sha256      text null
state                      text not null
previous_collection        text null
attempt_count              integer not null default 0
worker_id                  text null
lease_until                timestamptz null
error_code                 text null
created_at                 timestamptz not null
build_started_at           timestamptz null
validated_at               timestamptz null
activated_at               timestamptz null
completed_at               timestamptz null

unique(corpus_id, corpus_manifest_sha256, index_pipeline_fingerprint)
unique(physical_collection)
```

### 8.6 `publication_documents`

```text
publication_id       uuid not null references publications(id)
document_id          text not null
document_revision_id uuid not null references document_revisions(id)
primary key(publication_id, document_id)
```

Это immutable exact membership одной publication.

### 8.7 Никакой generic jobs table в v1

`publications` одновременно является:

- domain aggregate;
- durable work queue;
- recovery journal;
- operator status resource.

Не добавлять Celery task IDs, Redis Streams, RabbitMQ или вторую таблицу, дублирующую publication lifecycle.

---

## 9. Document mutation semantics

### 9.1 PUT/update

1. Стримить bytes в CAS.
2. В короткой PostgreSQL transaction:
   - найти/create document;
   - найти/create immutable revision по content hash;
   - обновить `desired_revision_id`;
   - снять `deleted_at`;
   - при `publish=true` заморозить новую publication.
3. Вернуть revision/publication identity.

Если DB transaction откатилась после успешной CAS write, может остаться unreferenced blob. Это безопасно; будущий GC удалит его после доказательства отсутствия references.

### 9.2 Повтор одинаковых bytes

```text
same document_id + same content_sha256
→ existing revision
→ no embedding
→ no duplicate points
```

Если desired corpus не изменился, новая publication не создаётся.

### 9.3 DELETE

```text
desired_revision_id = NULL
deleted_at = now()
```

DELETE никогда не вызывает direct Qdrant delete. Документ исчезает только из следующей immutable candidate collection.

### 9.4 Batch staging

`publish=false` позволяет выполнить несколько PUT/DELETE и затем один раз вызвать explicit publication. Это исключает N полных publications при bulk update.

---

## 10. Два fingerprints, не один

### 10.1 `index_pipeline_fingerprint`

Меняет Qdrant representation и требует нового physical target.

Включает:

- payload schema version;
- parser name/version;
- normalization policy version;
- chunker name/config;
- tokenizer model/revision;
- token ceiling;
- document embedding provider/model/instruction;
- dimensions;
- vector name;
- distance metric;
- Qdrant schema-affecting values.

### 10.2 `answer_pipeline_fingerprint`

Не требует document reindex, но меняет ответы/cache/evaluation identity.

Включает:

- query embedding request configuration;
- dense `top_k`;
- corpus filters;
- reranker model/request settings;
- rerank score threshold;
- completion model/provider settings;
- system/user prompt templates;
- structured answer schema;
- refusal policy version;
- citation/attribution validation policy version.

Не создавать четыре-пять overlapping fingerprints. Двух достаточно для честного разделения index representation и online answer behavior.

---

## 11. Deterministic identities

### 11.1 Document revision

```text
document_revision_id = UUID5(
  namespace(corpus_id, document_id),
  content_sha256
)
```

`source_version` — provenance, а не content identity. Новый commit/ETag с теми же bytes не заставляет переэмбеддить документ.

### 11.2 Corpus manifest

```text
corpus_manifest_sha256 = SHA256(
  canonical_json(
    sorted(document_id, document_revision_id, content_sha256)
  )
)
```

### 11.3 Index revision

```text
index_revision = SHA256(
  corpus_id
  + corpus_manifest_sha256
  + index_pipeline_fingerprint
)
```

### 11.4 Physical collection

```text
idx-<first-40-hex-of-SHA256(corpus_id:index_revision)>
```

### 11.5 Revision-bound point IDs

```text
pipeline_namespace = UUID5(corpus_id, index_pipeline_fingerprint)
source_id          = UUID5(pipeline_namespace, document_revision_id)
point_id           = UUID5(source_id, chunk_ordinal)
```

Следствия:

- unchanged revision + unchanged pipeline → same point IDs;
- changed document bytes → new revision and point IDs;
- changed chunker/embedding/schema → new namespace и полный rebuild;
- path rename не меняет ID;
- physical collection name не участвует в source identity.

---

## 12. Qdrant payload schema v3

Каждый point хранит строго валидируемый payload:

```text
record_type
schema_version
corpus_id
publication_id
corpus_manifest_sha256
index_pipeline_fingerprint
index_revision

document_id
document_revision_id
source_id
source_key
source_version
content_sha256

chunk_ordinal
chunk_sha256
raw_text
headings
```

Требования:

- exact key set;
- exact types;
- safe UTF-8 metadata;
- deterministic identity chain recomputed on read;
- non-empty raw text;
- natural chunk ordinal;
- valid hash shapes;
- no model-authored citation metadata.

Collection metadata дублирует только publication-level identity:

```text
schema_version
corpus_id
publication_id
corpus_manifest_sha256
index_pipeline_fingerprint
index_revision
embedding_model
embedding_dimensions
```

Новые writes используют v3. Старые v2 targets остаются readable во время dual-read migration и не мутируются в place.

---

## 13. Qdrant collection configuration

До загрузки points создать payload indexes только для реальных filters:

- `record_type`;
- `corpus_id`;
- `document_revision_id` — для document-level vector reuse.

Включить strict mode как минимум с запретом retrieval/update filtering по неиндексированным полям.

Не включать заранее:

- quantization;
- sparse vectors;
- ColBERT/multivectors;
- custom sharding;
- multiple replicas;
- HNSW tuning.

Каждое из этих решений требует измерения памяти, latency и retrieval regression на собственном Gold.

---

## 14. Publication state machine

```text
QUEUED
  → BUILDING
  → VALIDATING
  → READY
  → ACTIVE

Terminal/side states:
  FAILED
  SUPERSEDED
```

`READY` означает: physical candidate полностью построен и проверен, но alias ещё не переключён.

Worker claim выполняется короткой transaction:

```sql
SELECT id
FROM publications
WHERE state IN ('QUEUED', 'BUILDING', 'VALIDATING')
  AND (state = 'QUEUED' OR lease_until < now())
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Затем worker выставляет lease и commit. Вся тяжёлая работа выполняется вне DB transaction.

V1 запускает один worker, но `SKIP LOCKED` и lease сохраняют корректность при случайном втором worker или restart без добавления broker.

---

## 15. Freeze publication

В одной PostgreSQL transaction:

1. lock corpus row;
2. прочитать текущие desired document revisions;
3. вычислить canonical corpus manifest digest;
4. вычислить index revision/physical collection;
5. создать или найти idempotent publication;
6. вставить exact `publication_documents` membership;
7. commit.

После commit membership publication никогда не меняется, даже если пользователь сразу загрузил следующий revision.

Перед activation worker повторно проверяет, что publication всё ещё соответствует latest desired snapshot. Если появился более новый snapshot, готовый candidate получает `SUPERSEDED` и alias не переключается.

---

## 16. Candidate build modes

### 16.1 Обязательный full rebuild fallback

Full rebuild должен всегда оставаться рабочим и тестируемым. Он используется когда:

- это первая publication;
- изменился index fingerprint;
- active target имеет несовместимую schema;
- old payload нельзя строго декодировать;
- vector reuse validation не прошла;
- оператор явно запросил clean rebuild.

### 16.2 Document-level unchanged-vector reuse

Это единственная incremental optimization в v1. Не реализовывать chunk-level hash buckets, moved-chunk graph или in-place reconciliation.

Если active publication имеет тот же `index_pipeline_fingerprint`:

- unchanged document revision:
  - отфильтровать её points в active collection;
  - прочитать payload + vectors;
  - строго проверить revision/schema/identity/dimensions;
  - загрузить их в candidate collection без embedding call;
- changed/new revision:
  - прочитать original;
  - Docling parse/chunk;
  - embed;
  - upload;
- deleted revision:
  - не переносить.

При любой неоднозначности выполнить full rebuild, а не пытаться «починить» active collection.

Перед реализацией vector reuse измерить full rebuild. Если он дешёв для конкретного корпуса, reuse может быть вторым bounded delivery slice, а не blocker первого production выпуска.

---

## 17. Candidate validation

Alias switch запрещён до прохождения всех blocking layers.

### 17.1 Ledger/original integrity

- exact publication membership;
- каждый original существует;
- размер совпадает;
- SHA-256 совпадает;
- deleted/non-member revision отсутствует.

### 17.2 Chunk integrity

- каждый document даёт хотя бы один chunk;
- chunk text не пустой;
- token ceiling соблюдён;
- headings валидны;
- ordinals детерминированы;
- point IDs уникальны;
- `chunk_sha256` воспроизводим.

### 17.3 Vector integrity

- правильное vector name;
- правильная dimension;
- все значения finite;
- нет missing vector;
- reused vectors принадлежат совместимому fingerprint.

### 17.4 Exact Qdrant reconciliation

Использовать exact Count API и полный Scroll, а не approximate collection counters.

Доказать:

```text
expected_count == actual_exact_count
MISSING   = 0
EXTRA     = 0
STALE     = 0
INVALID   = 0
DUPLICATE = 0
```

Вычислить `point_manifest_sha256` из canonical sorted point identities и записать его в PostgreSQL.

### 17.5 Physical candidate smoke

Выполнить search/citation decoding непосредственно против physical collection, не через alias.

Smoke проверяет:

- collection queryable;
- filter indexes работают;
- payload декодируется;
- evidence/citation metadata валидны;
- candidate identity совпадает с publication.

LLM provider availability не является healthcheck, но controlled evaluation/smoke может вызывать реальный pipeline по явной operator policy.

---

## 18. Atomic activation и recovery

Единственный query visibility commit point — native Qdrant alias switch.

```text
old alias → old physical
candidate  → READY

atomic alias request

alias → candidate physical
```

После успешного switch worker обновляет PostgreSQL:

- candidate → `ACTIVE`;
- `corpora.active_publication_id` → candidate;
- previous → `SUPERSEDED`;
- сохраняет previous collection как rollback target.

### Crash windows

#### До alias switch

Пользователи продолжают видеть old valid index. Candidate можно безопасно продолжить или перестроить.

#### После alias switch, до PostgreSQL commit

Startup recovery:

1. прочитать actual alias target;
2. найти publication по `physical_collection`;
3. проверить, что она была `READY` и имеет valid reconciliation identity;
4. довести PostgreSQL до `ACTIVE`;
5. не потерять previous rollback target.

PostgreSQL остаётся authority document lifecycle, а Qdrant alias — authority только факта текущей search visibility.

---

## 19. Rollback и GC

Первое действие rollback:

```text
atomic alias → retained previous physical collection
```

Только затем reconcile PostgreSQL и, при необходимости, откатывать application image.

GC — отдельная destructive command. Она никогда не удаляет:

- current alias target;
- retained previous rollback target;
- non-terminal candidate;
- target, упомянутый active/recovery state.

Никакого автоматического удаления старой collection внутри успешной publication transaction.

---

## 20. RagApplication composition root

```python
class RagApplication:
    settings: Settings
    pg_pool: AsyncConnectionPool
    qdrant_client: AsyncQdrantClient
    openrouter_client: object
    cache_client: object | None
```

Он владеет resources для lifetime процесса и предоставляет application methods:

```text
execute(question, physical_collection=None) -> RagExecution
ask(question, physical_collection=None) -> GroundedAnswer
put_document(...)
delete_document(...)
request_publication()
get_publication(publication_id)
resolve_active_publication()
```

Это не DI container. Это один явный composition root.

FastAPI lifespan открывает/закрывает pool и SDK clients ровно один раз. CLI создаёт application на одну команду. Telegram создаёт application на polling lifetime. Evaluation создаёт clients на один run и вызывает public `execute`.

---

## 21. Process model

Один образ, разные commands:

```text
rag serve
rag worker
rag ask
rag ingest-git
rag bot
rag migrate
rag publication activate
rag publication rollback
```

### `rag-api`

- async FastAPI;
- process-long Psycopg pool;
- process-long async Qdrant/OpenRouter clients;
- online query path;
- streaming upload в CAS;
- создание durable publication rows;
- не парсит/чанкает/эмбеддит documents.

### `rag-worker`

- один process по умолчанию;
- claim publication через PostgreSQL;
- sync или async native SDK path без HTTP к API;
- Docling и embedding workload не конкурируют с API event loop;
- idempotent restart/recovery.

Не использовать FastAPI `BackgroundTasks` для publication. Не запускать тяжёлый worker thread внутри API процесса.

---

## 22. HTTP API v1

V1 обслуживает один configured `corpus_id`, поэтому routes не симулируют multi-tenancy.

### Health

```text
GET /health/live
GET /health/ready
```

`live` проверяет только процесс. `ready` проверяет:

- PostgreSQL connection;
- current migration version;
- Qdrant availability;
- active alias/ledger consistency, если active publication существует.

Readiness не вызывает OpenRouter/LLM.

### PUT document

```text
PUT /v1/documents/{document_id}?publish=true|false
Content-Type: text/markdown
Body: raw streamed UTF-8 Markdown bytes
Optional: X-Source-Version
```

Не использовать multipart и не добавлять `python-multipart`.

Response:

```json
{
  "document_id": "...",
  "revision_id": "...",
  "content_sha256": "...",
  "publication_id": "... or null",
  "changed": true
}
```

При publication request вернуть `202 Accepted`.

### DELETE document

```text
DELETE /v1/documents/{document_id}?publish=true|false
```

Меняет desired state; Qdrant напрямую не мутирует.

### Explicit publication

```text
POST /v1/publications
GET  /v1/publications/{publication_id}
```

Status response содержит только identity/state/counts/timestamps/sanitized error code.

### Ask

```text
POST /v1/ask
{
  "question": "..."
}
```

Перед execution API один раз разрешает alias в immutable physical target. Весь request использует этот target, чтобы публикация посередине запроса не смешала retrieval/cache identities.

Ответ:

```json
{
  "answer": "...",
  "grounded": true,
  "citations": [...],
  "publication": {
    "id": "...",
    "index_revision": "...",
    "physical_collection": "..."
  }
}
```

### Authentication

Все `/v1/*` защищены одним service bearer key.

- static key из secret environment;
- `secrets.compare_digest`;
- никаких JWT/users/refresh tokens;
- key не логируется;
- health endpoints могут иметь отдельную network policy.

---

## 23. Python API

Стабилизировать публичные immutable types:

```python
@dataclass(frozen=True, slots=True)
class Evidence:
    text: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class RagExecution:
    answer: GroundedAnswer
    dense_evidence: tuple[Evidence, ...]
    reranked_evidence: tuple[Evidence, ...]

    @property
    def generation_evidence(self) -> tuple[Evidence, ...]: ...
```

```python
async def execute(
    question: str,
    settings: Settings,
    *,
    client: object,
    qdrant_client: object,
    collection: str | None = None,
) -> RagExecution: ...
```

`ask()` остаётся convenience composition root. HTTP, CLI, Telegram и evaluation не создают свои pipeline variants.

---

## 24. Evaluation contract

DeepEval остаётся единственным semantic evaluation framework и отсутствует в production image/import graph.

Один Gold case выполняет production pipeline ровно один раз. Из одного `RagExecution` берутся exact views.

### 24.1 Deterministic layer

Без LLM judge:

- Recall@K;
- Precision@K;
- MRR;
- binary-gain nDCG;
- expected answerability;
- refusal correctness;
- citation identity correctness;
- selected evidence correctness.

Эти проверки являются authoritative для identity/ranking/citation invariants.

### 24.2 DeepEval five lanes

```text
Contextual Recall      → dense evidence
Contextual Precision   → ordered reranked evidence
Contextual Relevancy   → exact generation context
Faithfulness           → final answer vs exact generation context
Answer Relevancy       → question vs final answer
```

Сохранить calibrated GEval answer/refusal lane, если она остаётся частью frozen evaluator epoch.

Нельзя подставлять dense evidence, когда reranker вернул пустой список.

### 24.3 Run identity

Каждый run связывает:

- application Git SHA;
- corpus/publication/index identity;
- physical collection;
- `index_pipeline_fingerprint`;
- `answer_pipeline_fingerprint`;
- Gold manifest SHA-256;
- evaluator fingerprint;
- judge model/effort;
- DeepEval/Codex versions;
- metric policy version;
- timestamps/status.

Сравнение incompatible runs требует explicit declaration изменившейся dimension.

### 24.4 Threshold policy

Никакого универсального `0.8` или default `0.5` как production SLA.

Blocking threshold появляется только после:

- Ukrainian human-human agreement;
- judge-human agreement;
- variance repeats;
- boundary flip analysis;
- category-specific error review.

Неустойчивая lane остаётся diagnostic-only.

### 24.5 Change-class gates

#### Content-only update, same index pipeline

- deterministic integrity/reconciliation всегда;
- controlled retrieval smoke;
- DeepEval только если versioned policy требует.

#### Parser/chunker/embedding/vector/payload change

- full rebuild;
- full deterministic Gold;
- calibrated required DeepEval lanes;
- candidate остаётся `READY`, alias switch требует explicit activation после pass.

#### Top-k/reranker/prompt/generation-model change

- Qdrant rebuild не требуется;
- deterministic + соответствующие semantic lanes выполняются как release gate.

---

## 25. Optional Valkey cache

Cache не является correctness dependency и отсутствует из base install.

Использование: только exact grounded-answer cache.

```text
key = corpus_id
    + physical_collection
    + SHA256(exact question bytes)
    + answer_pipeline_fingerprint
```

Правила:

- alias разрешается один раз;
- тот же physical target используется для key и `execute`;
- кешируется только успешно grounded `GroundedAnswer`;
- refusals/failures не кешируются;
- malformed/wrong-identity entry = miss;
- Valkey недоступен = miss;
- cache error не меняет основной ответ;
- cancellation не подавляется;
- persistence на cache server отключена;
- TTL обязателен и положителен.

Не добавлять:

- semantic cache;
- RedisVL;
- cache warming;
- distributed locks;
- stampede framework;
- cache как queue;
- background invalidation.

---

## 26. Hybrid search и другие retrieval upgrades

Hybrid search не включать в baseline migration.

После document lifecycle/publication stabilization провести один controlled experiment:

```text
A: current dense + rerank
B: Qdrant native dense + sparse RRF + same rerank
```

Заморозить:

- corpus snapshot;
- Gold;
- generator;
- reranker;
- context budget;
- evaluator.

Сравнить:

- Recall@K;
- MRR;
- nDCG;
- Contextual Precision/Recall/Relevancy;
- Faithfulness;
- latency;
- provider/storage cost.

Если hybrid не даёт predeclared practical improvement, оставить dense baseline. Не добавлять sparse dependency «по лучшей практике» без результата на собственном корпусе.

Та же дисциплина применяется к quantization, chunk size, Qwen model, reranker и thresholds.

---

## 27. Dependencies

### Base core

Сохранить текущие pinned dependencies и добавить только:

```text
psycopg[binary]
psycopg-pool
```

### HTTP extra

```text
fastapi
uvicorn
```

Не использовать `uvicorn[standard]`, пока базовый сервер не упирается в measured throughput.

### Telegram extra

```text
aiogram
```

### Cache extra

```text
redis Python client
```

Сервер — Valkey-compatible digest-pinned image.

### Evaluation dependency group

```text
deepeval
openai-codex
```

Production API/worker image не содержит evaluation, Telegram и cache extras без явного выбора.

---

## 28. Configuration

Pydantic Settings остаётся единственным settings owner.

Добавить группы:

```text
RAG_DATABASE_URL
RAG_ORIGINALS_DIR
RAG_SERVICE_API_KEY
RAG_MAX_DOCUMENT_BYTES
RAG_WORKER_POLL_SECONDS
RAG_WORKER_LEASE_SECONDS
RAG_AUTO_ACTIVATE_CONTENT_UPDATES

RAG_CACHE_ENABLED
RAG_CACHE_URL
RAG_CACHE_TTL_SECONDS
```

Сохранить текущие OpenRouter/Qdrant/corpus values.

Дополнительно fail startup при неизвестной переменной с prefix `RAG_`, чтобы опечатка не silently ignored. Не вводить generic config registry.

Secrets остаются `SecretStr` и никогда не входят в fingerprints/logs.

---

## 29. Security и deployment

### Network

Production Compose:

- PostgreSQL — internal network, no host port;
- Qdrant — internal network, no public port;
- Valkey — internal profile, no host port;
- API — loopback или private reverse-proxy network;
- TLS termination — operator-owned Caddy/Nginx/ingress, не RAG core.

Даже internal self-hosted Qdrant получает API key. TLS обязателен при пересечении host/network boundary.

### Runtime

- non-root application user;
- read-only root filesystem где возможно;
- writable только originals/model cache/temp;
- digest-pinned infrastructure images;
- explicit memory/CPU ceilings;
- graceful SIGTERM;
- no secrets baked into image;
- no `latest` tags.

### Untrusted boundaries

- source bytes/metadata untrusted;
- Qdrant payload untrusted on read;
- model output untrusted;
- retrieved Markdown — evidence, не instructions;
- citation metadata только server-owned;
- private text не логируется.

---

## 30. Observability без framework overhead

Использовать stdlib `logging` и stable structured fields:

```text
request_id
publication_id
index_revision
physical_collection
stage
model
retrieved_count
reranked_count
selected_count
latency_ms
failure_code
```

Не логировать по умолчанию:

- document/chunk text;
- user question;
- generated answer;
- prompt;
- vector;
- credentials;
- Gold content.

OpenTelemetry, Prometheus, Sentry и hosted tracing не входят в v1. Добавлять их только при наличии операционного потребителя и требований.

---

## 31. Docker Compose

Required runtime:

```text
rag-api
rag-worker
postgres
qdrant
```

`rag-api` и `rag-worker` используют один image digest и разные commands.

Optional profile:

```text
cache → Valkey
```

Volumes:

```text
postgres_data
qdrant_data
rag_originals
huggingface_cache
```

Пример логического ownership:

```yaml
services:
  postgres:
    # internal, persistent, healthcheck

  qdrant:
    # internal, API key, persistent, healthcheck

  rag-api:
    # same application image, command: rag serve

  rag-worker:
    # same application image, command: rag worker

  valkey:
    profiles: [cache]
    # no persistence, disposable
```

Не добавлять Kubernetes, MinIO, PgBouncer, RabbitMQ, Kafka, Temporal, Qdrant Cloud или control-panel UI.

---

## 32. Backup и restore

Authoritative backup:

```text
PostgreSQL dump
+ originals tree
+ backup manifest/checksums
```

Backup обязательно копируется off-host. Qdrant snapshot — optional fast recovery, не единственный backup.

### Restore drill

1. Поднять clean PostgreSQL и empty Qdrant.
2. Восстановить PostgreSQL.
3. Восстановить originals.
4. Проверить migration/version/digests.
5. Запустить rebuild active desired snapshot.
6. Exact reconcile candidate.
7. Переключить alias.
8. Выполнить known question.
9. Получить grounded answer с citations.
10. Проверить exact expected `index_revision`/point manifest.

Backup, который ни разу не прошёл такой drill, не считается доказанным recovery path.

Qdrant image pinning и snapshot compatibility записываются в runbook.

---

## 33. Testing strategy

### 33.1 Hermetic base suite

Без Docker, Qdrant, PostgreSQL, OpenRouter, DeepEval и model download:

- canonical JSON;
- identities/fingerprints;
- snapshots;
- original store;
- ledger SQL behavior через narrow fakes только на transport edge;
- publication transitions;
- HTTP wire validation;
- answer/citation contracts;
- cache key/envelope.

Branch coverage: не ниже текущих 90%.

### 33.2 Disposable PostgreSQL integration

Проверить:

- same-content idempotency;
- immutable revisions;
- desired heads;
- delete history;
- publication freeze;
- concurrent claims;
- lease expiry/reclaim;
- migration integrity.

### 33.3 Disposable Qdrant integration

Проверить:

- fresh full build;
- compatible vector reuse;
- forced fallback rebuild;
- exact reconciliation;
- candidate query;
- atomic alias switch;
- rollback;
- safe GC exclusions.

### 33.4 HTTP E2E

```text
PUT document
→ publication ACTIVE
→ ask gives grounded answer
→ update document
→ new publication ACTIVE
→ old facts no longer visible
→ delete document
→ next publication omits it
```

### 33.5 Crash/failure matrix

Inject failure:

- before publication freeze;
- during CAS write;
- after DB commit;
- during parse;
- during embedding;
- during upload;
- after upload/before validation;
- after validation/before alias;
- after alias/before PostgreSQL;
- during GC.

Главный invariant:

```text
user sees old valid publication OR new valid publication
never a mixed/partial publication
```

---

## 34. Delivery plan и GitHub Issues

### Phase 0 — исправить architecture authority

Открытый PR #219 нельзя принимать без обновления: он всё ещё описывает FastAPI/PostgreSQL как deferred, тогда как новый продуктовый contract уже оформлен в #220–#224.

Обновить spec/plan в PR #219 или заменить его новым docs-only PR. Зафиксировать:

- Postgres как required control plane;
- FastAPI как thin product adapter;
- API/worker roles из одного image;
- one-clearance/one-deployment v1;
- Markdown-only v1;
- raw SQL/Psycopg, no ORM;
- full rebuild fallback;
- document-level vector reuse как bounded optimization;
- Qdrant/CAS/Postgres recovery authority.

### Phase 1 — #220

Document ledger и originals:

- snapshots;
- CAS;
- Psycopg pool;
- migrations;
- five core tables;
- Genesis adapter mapping;
- no HTTP changes.

### Phase 2 — #221

Publication engine:

- freeze;
- state machine;
- full rebuild;
- document-level reuse;
- exact validation;
- candidate search;
- alias switch;
- startup recovery;
- rollback/GC safety.

### Phase 3 — revised #222

Standalone product surface:

- `RagApplication`;
- `rag-api` + `rag-worker` roles from one image;
- FastAPI;
- static service auth;
- PUT/DELETE/publication/status/ask/health;
- existing CLI/Python/Telegram compatibility.

### Phase 4 — #223

Evaluation gate:

- Contextual Relevancy;
- unified run identity;
- comparator/policy;
- candidate physical target pinning;
- calibrated activation/release rules.

### Phase 5 — #224

Production VPS:

- Compose;
- network/security/resource limits;
- persistent volumes;
- off-host backup;
- full restore/rebuild drill.

### Phase 6 — #217

Optional exact Valkey cache после correctness path. Не blocker основного выпуска.

### Phase 7 — #52 experiments

Hybrid search, models, chunking, K и threshold только после frozen baseline.

---

## 35. Explicit non-goals v1

- LangChain;
- LlamaIndex;
- LangGraph;
- Haystack runtime;
- LiteLLM Proxy;
- SQLAlchemy ORM;
- Alembic;
- Celery;
- ARQ/Taskiq;
- Redis queue/Streams;
- RabbitMQ/Kafka/Temporal;
- Kubernetes;
- Qdrant HA cluster;
- MinIO/S3 requirement;
- UI/admin panel;
- multi-tenancy/RBAC/OAuth/SSO;
- PDF/DOCX/OCR;
- GraphRAG;
- agentic retrieval;
- semantic cache;
- automatic hyperparameter search;
- provider/vector-store registries;
- generic plugin framework;
- second semantic evaluation framework.

---

## 36. Definition of Done

Система считается готовой, когда доказано:

### Document lifecycle

- create/update/delete корректно меняют desired state;
- revision history immutable;
- same bytes не создают duplicate work.

### Publication correctness

- active collection никогда не мутируется обычным update/delete;
- candidate exact reconciled;
- failure до alias не меняет production;
- crash после alias восстанавливается из actual alias state;
- rollback начинается с alias.

### Rebuildability

- empty Qdrant полностью восстанавливается из PostgreSQL + originals;
- restore drill завершается cited answer и exact index identity.

### Online behavior

- Python/HTTP/Telegram используют один execution path;
- ответы grounded или safe refusal;
- citations только server-owned;
- request привязан к одному immutable physical target.

### Evaluation

- deterministic metrics и DeepEval привязаны к exact run identity;
- все пять RAG lanes используют правильные stage views;
- arbitrary universal thresholds отсутствуют;
- risky pipeline changes не активируются без required evidence.

### Operations/security

- Postgres/Qdrant/Valkey не exposed публично;
- Qdrant защищён ключом;
- production image не содержит evaluation tooling;
- logs не содержат private corpus/questions/answers/secrets;
- backup уходит off-host.

### Simplicity

- один repo/package/image;
- два process roles без HTTP между ними;
- нет broker, ORM, DI/framework registry;
- каждая новая dependency имеет конкретного production consumer;
- текущий dense+rerank baseline сохранён до измеренного experiment winner.

---

## 37. Финальная формула продукта

```text
Python 3.12 modular monolith
+ one package / one image
+ FastAPI thin adapter
+ separate worker process from the same image
+ direct Psycopg PostgreSQL ledger/queue
+ local content-addressed originals
+ Qdrant OSS immutable candidate collections
+ exact reconciliation
+ atomic aliases
+ native model SDKs
+ deterministic evaluation
+ DeepEval offline
+ optional exact Valkey cache
```

Главный архитектурный invariant:

> PostgreSQL и originals определяют, каким должен быть corpus. Qdrant является полностью восстанавливаемым поисковым представлением. Alias определяет, какой целиком проверенный индекс видят пользователи. Ни Qdrant, ни cache, ни модель не являются источником бизнес-истины.

---

## 38. Research basis

Спецификация сверена по состоянию на 29 августа 2026 года с:

- живым `yastman/genesis-rag-api` и его Issues/PR;
- официальной Qdrant документацией по production, aliases, indexing, security, incremental updates, hybrid queries и recovery;
- PostgreSQL documentation по `FOR UPDATE SKIP LOCKED`;
- Psycopg 3 pool lifecycle guidance;
- FastAPI lifespan и background-task guidance;
- DeepEval RAG/component/CI documentation;
- Docling chunking documentation;
- Valkey persistence/license documentation.
