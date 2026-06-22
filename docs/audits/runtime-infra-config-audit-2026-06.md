# Runtime Infrastructure Config Audit — Qdrant, Redis, Docling, Telegram

Status: proposed audit  
Date: 2026-06-22  
Related: #3009

## Scope

This audit checks the current local-first RAG architecture against the official
Qdrant, Redis/RedisVL, and Docling documentation. It focuses on likely
misconfiguration, structural cleanup, and safe refactor targets.

Canonical product decision for this audit:

```text
retrieval stays local-first:
  BGE-M3 full-output -> Qdrant hybrid + ColBERT -> Redis cache -> LLM generation
```

Non-goal: migrate embeddings to OpenRouter/API.

## External documentation reviewed

Qdrant:

- Hybrid and multi-stage queries: https://qdrant.tech/documentation/search/hybrid-queries/
- Vectors, sparse vectors, multivectors, datatypes: https://qdrant.tech/documentation/manage-data/vectors/
- Quantization: https://qdrant.tech/documentation/manage-data/quantization/
- Configuration and strict mode: https://qdrant.tech/documentation/operations/configuration/

Redis / RedisVL:

- Redis key eviction: https://redis.io/docs/latest/develop/reference/eviction/
- Redis persistence: https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
- RedisVL SemanticCache: https://redis.io/docs/latest/develop/ai/redisvl/user_guide/llmcache/
- RedisVL EmbeddingsCache: https://redis.io/docs/latest/develop/ai/redisvl/user_guide/embeddings_cache/

Docling:

- Hybrid chunking example: https://docling-project.github.io/docling/examples/hybrid_chunking/
- Chunking concept: https://docling-project.github.io/docling/concepts/chunking/
- Document converter reference: https://docling-project.github.io/docling/reference/document_converter/

---

## Executive findings

The local-first architecture is sound. The current BGE-M3 + Qdrant + Redis +
Docling stack matches the project goal better than an API-only embedding stack.
The most important work is not replacing the stack; it is making configuration
and ownership explicit.

High-confidence findings:

1. Qdrant hybrid RRF + nested prefetch + ColBERT multivector rerank is the right
   architecture for local BGE-M3 full-output.
2. Qdrant multivector `MaxSim` for ColBERT is correctly aligned with the official
   multivector docs.
3. Redis as a cache layer is appropriate, but the current `volatile-lfu` policy
   needs review because the project appears to mix cache keys, checkpoint keys,
   RedisVL indexes, and possibly operational state in one Redis instance.
4. Docling `HybridChunker` is the right chunking direction, but tokenizer parity
   with BGE-M3 should be made explicit.
5. Several infra modules are structurally too broad and should be split without
   changing behavior first.

Likely misconfiguration / drift:

1. `src/ingestion/unified/cli.py` hardcodes binary quantization for the base
   dense vector during bootstrap. This conflicts conceptually with the collection
   naming policy where `quantization_mode=off` should mean no quantized
   collection. If intentional, rename/document it; if not, move binary
   quantization to the `_binary` profile only.
2. `compose.yml` configures Redis as `--maxmemory-policy volatile-lfu`. Redis
   docs state `volatile-*` policies only evict keys that have TTL; if RedisVL
   index keys, checkpoint keys, or other operational keys have no TTL, Redis can
   behave like `noeviction` for those keys under memory pressure.
3. `compose.yml` Docling service sets `DOCLING_PDF_BACKEND=dlparse_v2`, while
   `DoclingConfig` defaults to `dlparse_v4`. This is configuration drift.
4. `NativeDoclingAdapter` uses `HybridChunker(max_tokens=...)` but does not
   explicitly configure a HuggingFace tokenizer matching `BAAI/bge-m3`. Docling
   docs recommend matching the chunker tokenizer to the embedding model in a RAG
   context.
5. Qdrant payload indexes include many legacy/catalog fields. Because indexed
   payload fields remain memory-resident even with `on_disk_payload`, unused
   indexes should be periodically audited and removed from the canonical document
   collection.

---

## 1. Qdrant audit

### What is correct

The current schema direction is correct for BGE-M3 full-output:

```text
dense   -> 1024 cosine
bm42    -> sparse vector
colbert -> 1024 multivector MaxSim
```

Qdrant's Query API supports prefetches and nested prefetches. This matches the
current three-stage retrieval design:

```text
stage 1: dense prefetch + sparse prefetch
stage 2: RRF fusion
stage 3: ColBERT MaxSim over pre-stored multivectors
```

Qdrant's docs describe multivectors as a fit for late-interaction embeddings
such as ColBERT, and currently support `max_sim` as the comparator. The current
`colbert` vector config is aligned with that.

Strict mode is also a good guardrail. The current runtime applies:

```text
max_query_limit = 100
max_timeout = 30
search_max_hnsw_ef = 512
```

This is consistent with the purpose of Qdrant strict-mode options: limiting
query size, timeout, and search cost.

### Potential issue: binary quantization in base bootstrap

In `src/ingestion/unified/cli.py`, the bootstrap path creates the dense vector
with binary quantization:

```python
"dense": VectorParams(
    size=1024,
    distance=Distance.COSINE,
    hnsw_config=HnswConfigDiff(m=16, ef_construct=200, on_disk=False),
    quantization_config=BinaryQuantization(
        binary=BinaryQuantizationConfig(always_ram=True)
    ),
    on_disk=True,
)
```

This is risky as the default/base schema because the project also has a
collection naming policy for `off`, `scalar`, and `binary` collections. The base
collection should probably be full precision unless the name clearly communicates
that binary quantization is active.

Qdrant's quantization docs say binary quantization is aggressive: it can reduce
memory substantially and be fast, but it is best suited for high-dimensional,
centered vector distributions; Qdrant also recommends rescoring for binary
quantization, and notes that rescoring can slow down search when original vectors
are stored on disk.

### Recommendation

Split quantization into explicit profiles:

```text
gdrive_documents_bge          -> full precision / no binary quantization
gdrive_documents_bge_scalar   -> scalar quantization evaluation
gdrive_documents_bge_binary   -> binary quantization evaluation
```

Concrete tasks:

- [ ] Move dense `BinaryQuantization` out of the default bootstrap path.
- [ ] Add `--quantization-mode off|scalar|binary` to bootstrap, or derive from
      collection name policy.
- [ ] Add a schema check that fails if `quantization_mode=off` but binary
      quantization is present.
- [ ] Benchmark recall/latency for off vs scalar vs binary before making binary
      the production default.

### Potential issue: magic retrieval limits

`hybrid_search_rrf_colbert()` has useful defaults but hides important policy in
code:

```text
effective_dense_limit  ~= 100
effective_sparse_limit ~= 100
rrf_limit              = max(top_k * 4, 20)
```

These should become config values:

```env
QDRANT_DENSE_PREFETCH_LIMIT=100
QDRANT_SPARSE_PREFETCH_LIMIT=100
QDRANT_RRF_PREFETCH_LIMIT=50
QDRANT_RRF_K=60
```

### Potential issue: payload indexes and RAM

`docker/qdrant/config.yaml` enables `on_disk_payload: true`, which is a good
local-memory optimization. The file correctly notes that indexed payload fields
still live in memory. The Qdrant stack docs already categorize runtime-required
vs legacy/CSV/apartment-only fields. The next step is to ensure the default
`gdrive_documents_bge` document collection only indexes fields actually used by
runtime filters/grouping/deletes/citation lookup.

Suggested action:

- [ ] Add `make qdrant-index-audit` that reports payload indexes and whether the
      runtime uses them.
- [ ] Remove legacy-only payload indexes from the canonical document collection,
      or move them to a catalog-specific collection.

### Qdrant target structure

```text
src/runtime/qdrant/
  client.py
  schema.py
  aliases.py
  strict_mode.py
  filters.py
  results.py
  rrf.py
  colbert.py
  service.py
```

---

## 2. Redis / RedisVL audit

### What is correct

Redis is valuable for this local-first architecture because BGE-M3 query
embedding is expensive. The project already has the right cache tiers:

```text
semantic cache
embedding cache
sparse embedding cache
BGE-M3 query bundle cache
search result cache
rerank result cache
conversation/history cache
```

RedisVL `EmbeddingsCache` supports TTL and async operations. RedisVL
`SemanticCache` is appropriate for response reuse when guarded by query type,
role, grounding mode, filter signatures, and safe-reuse tags.

### Potential issue: `volatile-lfu` for mixed Redis workloads

`compose.yml` starts Redis with:

```text
--maxmemory ${REDIS_MAXMEMORY:-256mb}
--maxmemory-policy volatile-lfu
--maxmemory-samples 10
```

Redis docs state that `volatile-*` eviction policies only evict keys that have an
expiration/TTL. They also state that volatile policies can behave like
`noeviction` if no suitable expiring keys are available.

This is okay only if every memory-heavy cache key has TTL and non-cache state is
small. It becomes risky if the same Redis instance stores any of:

- RedisVL index/hash metadata without TTL
- checkpoint keys without TTL
- handoff/session state without TTL
- operational locks
- long-lived conversation state

### Recommendation

Decide the role of Redis explicitly.

Option A — Redis is cache-only:

```text
maxmemory-policy allkeys-lfu
```

This makes Redis free to evict any key. Use only if all Redis data is disposable
or recoverable.

Option B — Redis is mixed cache + operational state:

```text
Keep volatile-lfu, but enforce TTL on all cache keys and move operational state
that must not be evicted to Postgres or a separate Redis instance/db.
```

Recommended local-first project stance:

```text
Redis cache instance:
  allkeys-lfu, disposable cache data only

Persistent state:
  PostgreSQL, not Redis
```

If keeping one Redis instance, add startup checks:

- [ ] `CONFIG GET maxmemory-policy`
- [ ] scan/report keys without TTL by prefix
- [ ] fail or warn if cache prefixes produce non-TTL keys
- [ ] warn if `used_memory / maxmemory > 0.8`
- [ ] warn if `evicted_keys` increases

### Potential issue: memory headroom

Redis docs recommend leaving memory headroom when persistence/replication is
enabled because buffers are not counted the same way as cache data. Current
Compose has:

```text
redis maxmemory default: 256mb
container memory limit: 300M
```

That leaves about 44 MB for process overhead and buffers. This may be tight if
RedisVL creates indexes and search structures.

Recommended:

```text
REDIS_MAXMEMORY=256mb with container limit >=384M
or
REDIS_MAXMEMORY=192mb with container limit 300M
```

### Potential issue: persistence expectations

Redis persistence docs distinguish RDB and AOF tradeoffs. Current Redis has a
volume and defaults, but no explicit AOF policy in Compose. That is fine for
cache-only usage. It is not fine if Redis stores important non-reconstructable
workflow state.

Recommendation:

- [ ] document Redis as cache-only, or
- [ ] enable AOF for important Redis state, or
- [ ] move important state to Postgres.

### Redis target structure

```text
src/runtime/cache/
  manager.py
  keys.py
  semantic.py
  embeddings.py
  sparse.py
  search_results.py
  rerank.py
  conversation.py
  metrics.py
  health.py
```

Move `telegram_bot/services/redis_monitor.py` to `src/runtime/cache/health.py`.
Telegram should consume it, not own it.

---

## 3. Docling / ingestion audit

### What is correct

The move to Docling `HybridChunker` is correct. Docling docs describe hybrid
chunking as tokenization-aware refinement on top of document-based hierarchical
chunking. The examples also show `chunker.contextualize(chunk)` as the text that
is typically embedded.

`NativeDoclingAdapter` is well designed in several ways:

- lazy imports
- dependency injection for tests
- chunker created lazily
- supports contextualized text
- preserves `DoclingChunk` contract

### Potential issue: tokenizer mismatch with BGE-M3

Docling docs explicitly say that in a RAG/retrieval context it is important to
make sure the chunker and embedding model are using the same tokenizer.

Current `NativeDoclingAdapter` does:

```python
HybridChunker(max_tokens=self._max_tokens, merge_peers=True)
```

It does not explicitly configure a HuggingFace tokenizer for `BAAI/bge-m3`.
This can create chunk size drift between what Docling thinks is `N` tokens and
what BGE-M3 actually sees.

Recommendation:

- [ ] Configure Docling `HybridChunker` with a HuggingFace tokenizer based on
      `BGE_M3_MODEL=BAAI/bge-m3`.
- [ ] Use the same `max_tokens` policy for chunking and BGE-M3 `max_length`, or
      document why they differ.
- [ ] Add a regression test that representative RU/UK chunks do not exceed the
      configured BGE-M3 token budget.

Target pattern:

```python
from transformers import AutoTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.chunking import HybridChunker

tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained("BAAI/bge-m3"),
    max_tokens=max_tokens,
)
chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)
```

### Potential issue: Docling backend drift

`DoclingConfig` defaults to:

```text
pdf_backend = dlparse_v4
table_mode = accurate
profile default = speed
```

`compose.yml` sets:

```text
DOCLING_PDF_BACKEND=dlparse_v2
DOCLING_TABLE_MODE=accurate
```

This is drift. If `dlparse_v2` is intentional for the docling service image,
then document why it differs from the Python client default. Otherwise align it.

Recommendation:

- [ ] choose one canonical backend version for local ingestion
- [ ] expose `DOCLING_PROFILE=speed|quality|scan|vlm`
- [ ] make compose and `DoclingConfig` agree
- [ ] add preflight output that prints the effective Docling backend/profile

### Potential issue: CLI owns too much implementation

`src/ingestion/unified/cli.py` owns preflight, schema check, bootstrap, payload
index creation, reprocess, and ColBERT coverage/backfill. This makes it hard to
unit-test and reuse.

Split target:

```text
src/ingestion/unified/
  cli.py
  commands/
    preflight.py
    bootstrap.py
    schema_check.py
    status.py
    reprocess.py
    coverage.py
    backfill_colbert.py
  qdrant_schema.py
  preflight.py
  reprocess.py
```

---

## 4. Telegram audit

### Current state

`telegram_bot/bot.py` is explicitly described as a legacy compatibility surface.
It preserves historical imports through thin wrappers while helper modules are
being extracted.

That direction is good. Continue it.

### What to fix next

The main hotspot is `telegram_bot/_bot_query_pipeline.py`. It mixes:

- handoff gate
- apartment fast path
- client direct path adapter
- pre-agent semantic cache
- supervisor runner
- streaming recovery
- rendering/sending
- trace metadata
- postprocessing/cache store

Split target:

```text
telegram_bot/query/
  entrypoint.py
  handoff_gate.py
  apartment_fast_path.py
  client_direct_adapter.py
  pre_agent_cache.py
  supervisor_runner.py
  response_sender.py
  trace_metadata.py
```

Other Telegram splits:

```text
telegram_bot/catalog/
  services_callbacks.py
  card_callbacks.py
  faq_callbacks.py
  viewing_callbacks.py

telegram_bot/agents/
  agent.py       # factory/facade only
  prompts.py     # fallback prompt constants or prompt-manager defaults
```

Move apartment parsing out of Telegram if it is domain logic:

```text
src/domain/apartments/query_parser.py
telegram_bot/services/apartment_filter_legacy_adapter.py
```

### Keep

- Telegram handlers/dialogs/rendering in `telegram_bot`.
- CRM/HITL UX in Telegram adapter.
- `PropertyBot` as composition root.

### Move out

- reusable query parsing
- deterministic client direct runtime
- Redis health monitor
- prompt copy if prompt manager owns product prompts
- shared runtime/retrieval/cache logic

---

## Immediate action checklist

High priority:

- [ ] Add canonical local BGE-M3 architecture doc.
- [ ] Verify whether base Qdrant collection is unintentionally binary-quantized.
- [ ] Decide Redis role: cache-only vs mixed cache/state.
- [ ] Align Docling backend version between compose and `DoclingConfig`.
- [ ] Configure Docling chunker tokenizer to match `BAAI/bge-m3`.

Medium priority:

- [ ] Split `_bot_query_pipeline.py` into `telegram_bot/query/`.
- [ ] Split ingestion CLI command implementations.
- [ ] Extract Qdrant schema/RRF/ColBERT helpers.
- [ ] Extract Redis cache key builders and tier modules.

Low priority / after behavior freezes:

- [ ] Collapse remaining `telegram_bot` / `src` shims from ADR #2855.
- [ ] Move long prompts out of Python factory files.
- [ ] Audit unused Qdrant payload indexes.

---

## Recommended first PR from this audit

First PR should be documentation and guardrails only:

```text
PR: docs: add runtime infra config audit

Files:
  docs/audits/runtime-infra-config-audit-2026-06.md

No runtime changes.
```

Second PR should be the safest config guard:

```text
PR: test: assert bge_m3_full qdrant schema and quantization mode

Adds tests that verify:
  - dense vector exists
  - bm42 sparse exists
  - colbert multivector exists
  - base collection does not silently apply binary quantization unless profile says binary
```
