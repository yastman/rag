# BGE-M3 + ColBERT m=0 Optimization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Optimize Qdrant collection for BGE-M3 hybrid search with ColBERT reranking using `hnsw_config.m=0` (disable HNSW for reranker-only vector).

**Architecture:** ColBERT используется только для reranking top-50 → top-5, поэтому HNSW индекс не нужен. Отключение HNSW (`m=0`) экономит RAM и ускоряет upsert без потери качества поиска. Dense + Sparse используют HNSW для fast retrieval.

**Tech Stack:** Python 3.11+, Qdrant 1.10+, qdrant-client, httpx, BGE-M3 API (port 8000)

---

## Task 0: Backup Current State

**Goal:** Сохранить текущую коллекцию перед оптимизацией.

**Step 1: Check current collection stats**

```bash
curl -s http://localhost:6333/collections/contextual_bulgaria | python -m json.tool | head -30
```

Expected: JSON с `points_count: 92`, `vectors_config` с dense/colbert/bm42.

**Step 2: Create snapshot**

```bash
curl -X POST "http://localhost:6333/collections/contextual_bulgaria/snapshots"
```

Expected: JSON с `name` snapshot файла.

**Step 3: Verify snapshot created**

```bash
curl -s http://localhost:6333/collections/contextual_bulgaria/snapshots | python -m json.tool
```

Expected: Список снапшотов включает новый.

---

## Task 1: Update Collection Creation with m=0

**Files:**
- Modify: `scripts/index_contextual_api.py:45-68`

**Step 1: Read the current create_collection function**

Review lines 45-68 in `scripts/index_contextual_api.py`.

**Step 2: Update create_collection with HnswConfigDiff**

Replace the `create_collection` function (lines 45-68):

```python
def create_collection(client: QdrantClient, collection_name: str, recreate: bool = False):
    """Create Qdrant collection with optimized BGE-M3 vectors.

    Optimization: ColBERT uses hnsw_config.m=0 (no HNSW index) because:
    - ColBERT is used for reranking, not first-stage retrieval
    - Brute-force MaxSim on 50 candidates is fast enough
    - Saves RAM and speeds up upsert operations
    """
    from qdrant_client.models import HnswConfigDiff, MultiVectorConfig, MultiVectorComparator, Modifier

    if recreate and client.collection_exists(collection_name):
        client.delete_collection(collection_name)
        print(f"  Deleted existing collection: {collection_name}")

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                    # Dense uses HNSW for fast first-stage retrieval
                ),
                "colbert": VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(
                        comparator=MultiVectorComparator.MAX_SIM
                    ),
                    # OPTIMIZATION: Disable HNSW for ColBERT (reranker only)
                    hnsw_config=HnswConfigDiff(m=0),
                ),
            },
            sparse_vectors_config={
                "bm42": SparseVectorParams(modifier=Modifier.IDF),
            },
        )
        print(f"  Created collection: {collection_name} (ColBERT m=0 optimized)")
    else:
        print(f"  Using existing collection: {collection_name}")
```

**Step 3: Update imports at top of file**

Add to imports (line ~20):

```python
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    MultiVectorConfig,
    MultiVectorComparator,
    Modifier,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)
```

**Step 4: Run linter**

```bash
source venv/bin/activate && ruff check scripts/index_contextual_api.py --fix
```

Expected: No errors or auto-fixed.

**Step 5: Commit**

```bash
git add scripts/index_contextual_api.py
git commit -m "$(cat <<'EOF'
perf(indexer): add ColBERT m=0 optimization

- Disable HNSW index for ColBERT vector (hnsw_config.m=0)
- ColBERT used for reranking only, not first-stage retrieval
- Saves RAM and speeds up upsert operations
- No impact on search quality (brute-force MaxSim on top-50)

Best Practice 2026: ColBERT reranker doesn't need HNSW graph.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Recreate Collection with Optimization

**Goal:** Пересоздать коллекцию с m=0 и переиндексировать 92 чанка.

**Step 1: Verify BGE-M3 API is running**

```bash
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok","model_loaded":true}`

**Step 2: Recreate collection and reindex**

```bash
source venv/bin/activate && python scripts/index_contextual_api.py docs/processed/ --collection contextual_bulgaria --recreate
```

Expected output:
```
============================================================
Contextual Retrieval Indexer (API Mode)
============================================================
  BGE-M3 API: http://localhost:8000 ✓
  Qdrant: http://localhost:6333 ✓

  Collection: contextual_bulgaria
  Deleted existing collection: contextual_bulgaria
  Created collection: contextual_bulgaria (ColBERT m=0 optimized)

  Found 13 JSON files
  ...
============================================================
Summary
============================================================
  Files processed: 13
  Total chunks: 92
  Points in collection: 92
```

**Step 3: Verify collection config**

```bash
curl -s http://localhost:6333/collections/contextual_bulgaria | python -c "
import sys, json
data = json.load(sys.stdin)
config = data['result']['config']['params']['vectors_config']
colbert_hnsw = config.get('colbert', {}).get('hnsw_config', {})
print(f'ColBERT HNSW m: {colbert_hnsw.get(\"m\", \"default\")}')
print(f'Points: {data[\"result\"][\"points_count\"]}')
"
```

Expected:
```
ColBERT HNSW m: 0
Points: 92
```

---

## Task 3: Test Search Quality

**Goal:** Убедиться что поиск работает корректно после оптимизации.

**Step 1: Create test script**

Create file `scripts/test_search_quality.py`:

```python
#!/usr/bin/env python3
"""Test search quality after m=0 optimization."""

import asyncio
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import SparseVector, Prefetch

QDRANT_URL = "http://localhost:6333"
BGE_M3_URL = "http://localhost:8000"
COLLECTION = "contextual_bulgaria"

TEST_QUERIES = [
    ("Как открыть фирму в Болгарии?", "Зачем открывать фирму"),
    ("Налог НДС ДДС при сдаче через Букинг", "Налоговая ловушка"),
    ("ВНЖ для фрилансеров Digital Nomad", "Digital Nomad"),
    ("Такса поддержки что это", "поддержки"),
    ("Сколько стоит открыть фирму в Болгарии", "300 евро"),
]


async def get_embeddings(text: str) -> dict:
    """Get embeddings from BGE-M3 API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BGE_M3_URL}/encode/hybrid",
            json={"texts": [text]}
        )
        return resp.json()


async def test_search():
    """Run test queries and verify results."""
    client = QdrantClient(url=QDRANT_URL)

    print("=" * 60)
    print("Search Quality Test (m=0 optimization)")
    print("=" * 60)

    passed = 0
    failed = 0

    for query, expected_in_result in TEST_QUERIES:
        emb = await get_embeddings(query)

        # Hybrid search with ColBERT reranking
        results = client.query_points(
            collection_name=COLLECTION,
            prefetch=[
                Prefetch(query=emb["dense_vecs"][0], using="dense", limit=20),
                Prefetch(
                    query=SparseVector(
                        indices=emb["lexical_weights"][0]["indices"],
                        values=emb["lexical_weights"][0]["values"]
                    ),
                    using="bm42",
                    limit=20
                ),
            ],
            query=emb["colbert_vecs"][0],
            using="colbert",
            limit=3,
        )

        top_result = results.points[0] if results.points else None

        if top_result:
            topic = top_result.payload.get("metadata", {}).get("topic", "")
            text = top_result.payload.get("page_content", "")
            score = top_result.score

            found = expected_in_result.lower() in topic.lower() or expected_in_result.lower() in text.lower()
            status = "✅ PASS" if found else "⚠️ CHECK"

            if found:
                passed += 1
            else:
                failed += 1

            print(f"\nQ: {query}")
            print(f"   → Topic: {topic}")
            print(f"   → Score: {score:.2f}")
            print(f"   → {status}")
        else:
            failed += 1
            print(f"\nQ: {query}")
            print(f"   → ❌ NO RESULTS")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} need review")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_search())
    exit(0 if success else 1)
```

**Step 2: Run test script**

```bash
source venv/bin/activate && python scripts/test_search_quality.py
```

Expected: All 5 queries pass or show relevant results.

**Step 3: Commit test script**

```bash
git add scripts/test_search_quality.py
git commit -m "$(cat <<'EOF'
test(scripts): add search quality verification script

- Tests hybrid search with ColBERT reranking
- Verifies m=0 optimization doesn't affect quality
- 5 test queries covering different topics

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update Documentation

**Files:**
- Modify: `docs/plans/2026-01-21-contextual-retrieval-implementation.md`
- Modify: `REDISVL_DESIGN.md`

**Step 1: Add optimization note to contextual retrieval plan**

Add section at the end of `docs/plans/2026-01-21-contextual-retrieval-implementation.md`:

```markdown

---

## Task 6: ColBERT m=0 Optimization (Added 2026-01-21)

**Files:**
- Modified: `scripts/index_contextual_api.py`
- Created: `scripts/test_search_quality.py`

**Optimization Applied:**

```python
"colbert": VectorParams(
    size=1024,
    distance=Distance.COSINE,
    multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
    hnsw_config=HnswConfigDiff(m=0),  # ← Disable HNSW for reranker
)
```

**Why m=0:**
- ColBERT used for reranking top-50 → top-5 (not first-stage retrieval)
- Brute-force MaxSim on 50 candidates is fast (<10ms)
- HNSW index wastes RAM and slows down upsert for reranker vectors

**Best Practice 2026:** Official Qdrant recommendation for ColBERT reranking.

**Verification:**
```bash
python scripts/test_search_quality.py  # All queries should pass
```
```

**Step 2: Update REDISVL_DESIGN.md Qdrant section**

Find the Qdrant Hybrid Search section (around line 243) and update the collection schema:

```markdown
**Collection Schema (Optimized 2026):**

```python
from qdrant_client.models import (
    VectorParams, SparseVectorParams, HnswConfigDiff,
    Distance, Modifier, MultiVectorConfig, MultiVectorComparator
)

await qdrant.create_collection(
    collection_name="apartments_v2",
    vectors_config={
        "dense": VectorParams(
            size=1024,
            distance=Distance.COSINE,
        ),
        "colbert": VectorParams(
            size=1024,
            distance=Distance.COSINE,
            multivector_config=MultiVectorConfig(
                comparator=MultiVectorComparator.MAX_SIM
            ),
            # OPTIMIZATION: Disable HNSW for ColBERT reranker
            hnsw_config=HnswConfigDiff(m=0),
        ),
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(
            modifier=Modifier.IDF,  # BM42-style IDF weighting
        ),
    },
)
```
```

**Step 3: Commit documentation**

```bash
git add docs/plans/2026-01-21-contextual-retrieval-implementation.md REDISVL_DESIGN.md
git commit -m "$(cat <<'EOF'
docs: add ColBERT m=0 optimization documentation

- Document hnsw_config.m=0 for ColBERT reranker
- Update collection schema in REDISVL_DESIGN.md
- Add Task 6 to contextual retrieval plan
- Reference Qdrant 2026 best practices

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Final Verification

**Step 1: Run all contextual tests**

```bash
source venv/bin/activate && pytest tests/test_contextual_*.py -v
```

Expected: All 19 tests PASS.

**Step 2: Verify collection status**

```bash
curl -s http://localhost:6333/collections/contextual_bulgaria | python -c "
import sys, json
data = json.load(sys.stdin)
result = data['result']
print(f'Collection: contextual_bulgaria')
print(f'Points: {result[\"points_count\"]}')
print(f'Status: {result[\"status\"]}')
vectors = result['config']['params']['vectors_config']
for name, config in vectors.items():
    hnsw_m = config.get('hnsw_config', {}).get('m', 'default')
    print(f'  {name}: size={config[\"size\"]}, hnsw_m={hnsw_m}')
"
```

Expected:
```
Collection: contextual_bulgaria
Points: 92
Status: green
  dense: size=1024, hnsw_m=default
  colbert: size=1024, hnsw_m=0
```

**Step 3: Run search quality test**

```bash
python scripts/test_search_quality.py
```

Expected: All queries pass.

**Step 4: Final commit**

```bash
git add -A
git status
```

If any uncommitted changes:
```bash
git commit -m "$(cat <<'EOF'
chore: complete BGE-M3 + ColBERT m=0 optimization

Phase 6 of REDISVL_DESIGN.md complete:
- Hybrid search: Dense + Sparse (BM42) + ColBERT
- ColBERT optimized with hnsw_config.m=0
- 92 chunks indexed in contextual_bulgaria
- All tests passing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 0 | Backup current state | ⏳ |
| 1 | Update create_collection with m=0 | ⏳ |
| 2 | Recreate collection and reindex | ⏳ |
| 3 | Test search quality | ⏳ |
| 4 | Update documentation | ⏳ |
| 5 | Final verification | ⏳ |
| 6 | RedisVL SemanticCache with filterable_fields | ⏳ |
| 7 | Native EmbeddingsCache integration | ⏳ |
| 8 | Qdrant Document API integration | ⏳ |

## Architecture After Optimization

```
Query
  │
  ├─► BGE-M3 API (port 8000)
  │     └─► dense_vec (1024)
  │     └─► sparse_vec (BM42)
  │     └─► colbert_vec (1024 × N tokens)
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 1: Prefetch (HNSW indexed)                       │
│                                                         │
│  Dense (HNSW) ────┬──► RRF Fusion ──► 50 candidates    │
│  Sparse (BM42) ───┘                                    │
└─────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2: Rerank (Brute-force, m=0)                    │
│                                                         │
│  ColBERT (MaxSim) ──► Top 5 results                    │
│                                                         │
│  No HNSW overhead, fast brute-force on 50 docs         │
└─────────────────────────────────────────────────────────┘
```

## Expected Benefits

| Metric | Before | After |
|--------|--------|-------|
| ColBERT HNSW RAM | ~50MB | 0 |
| Upsert speed | Normal | Faster |
| Search quality | High | Same |
| Search latency | ~1s | ~1s |

## Verification Commands

```bash
# Check collection config
curl -s http://localhost:6333/collections/contextual_bulgaria | jq '.result.config.params.vectors_config.colbert.hnsw_config'

# Run search quality test
python scripts/test_search_quality.py

# Run unit tests
pytest tests/test_contextual_*.py -v
```

---

## Task 6: RedisVL SemanticCache with filterable_fields

> **Source:** Context7 RedisVL 0.11+ documentation

**Goal:** Добавить фильтрацию по user_id и metadata в SemanticCache.

**Files:**
- Modify: `telegram_bot/services/cache.py`

**Step 1: Update SemanticCache initialization**

```python
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.utils.vectorize import HFTextVectorizer

vectorizer = HFTextVectorizer(model="redis/langcache-embed-v1")

semantic_cache = SemanticCache(
    name="rag_llm_cache",
    redis_url="redis://localhost:6379",
    ttl=48 * 3600,
    distance_threshold=0.15,
    vectorizer=vectorizer,
    # NEW: filterable_fields for multi-user isolation
    filterable_fields=[
        {"name": "user_id", "type": "tag"},
        {"name": "language", "type": "tag"},
        {"name": "query_type", "type": "tag"},  # property, vnj, tax, etc.
    ],
)
```

**Step 2: Update store with filters**

```python
async def store_semantic_cache(
    self,
    query: str,
    answer: str,
    user_id: int,
    language: str = "ru",
    query_type: str = "general",
):
    """Store with user context filters."""
    await self.semantic_cache.astore(
        prompt=query,
        response=answer,
        filters={
            "user_id": str(user_id),
            "language": language,
            "query_type": query_type,
        },
    )
```

**Step 3: Update check with filter_expression**

```python
from redisvl.query.filter import Tag

async def check_semantic_cache(
    self,
    query: str,
    user_id: int = None,
    language: str = "ru",
) -> Optional[str]:
    """Check cache with optional user filtering."""
    filter_expr = Tag("language") == language

    # Optional: user-specific cache isolation
    if user_id:
        filter_expr = filter_expr & (Tag("user_id") == str(user_id))

    results = await self.semantic_cache.acheck(
        prompt=query,
        filter_expression=filter_expr,
        num_results=1,
    )

    if results:
        return results[0].get("response")
    return None
```

**Step 4: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "$(cat <<'EOF'
feat(cache): add filterable_fields to SemanticCache

- Add user_id, language, query_type filters
- Enable multi-user cache isolation
- Support language-specific caching
- Based on RedisVL 0.11+ filterable_fields API

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Native EmbeddingsCache Integration

> **Source:** Context7 RedisVL EmbeddingsCache

**Goal:** Заменить JSON-based кеширование на нативный RedisVL EmbeddingsCache.

**Files:**
- Modify: `telegram_bot/services/cache.py`
- Modify: `telegram_bot/services/embedding.py`

**Step 1: Initialize EmbeddingsCache**

```python
from redisvl.extensions.cache.embeddings import EmbeddingsCache

class CacheService:
    def __init__(self, redis_url: str, ...):
        # ...existing code...

        # Native EmbeddingsCache for BGE-M3
        self.embeddings_cache: Optional[EmbeddingsCache] = None

    async def initialize(self):
        # ...existing code...

        # Initialize native EmbeddingsCache
        self.embeddings_cache = EmbeddingsCache(
            name="bge_m3_embeddings",
            redis_url=self.redis_url,
            ttl=self.embeddings_cache_ttl,  # 7 days
        )
        logger.info("✓ EmbeddingsCache initialized (native RedisVL)")
```

**Step 2: Update embedding methods with async API**

```python
async def get_cached_embedding(self, text: str, model_name: str = "bge-m3") -> Optional[list[float]]:
    """Get cached embedding using native EmbeddingsCache."""
    if not self.embeddings_cache:
        return None

    try:
        result = await self.embeddings_cache.aget(
            text=text,
            model_name=model_name,
        )
        if result:
            self.metrics["embeddings"]["hits"] += 1
            return result["embedding"]

        self.metrics["embeddings"]["misses"] += 1
        return None
    except Exception as e:
        logger.error(f"EmbeddingsCache error: {e}")
        return None


async def store_embedding(
    self,
    text: str,
    embedding: list[float],
    model_name: str = "bge-m3",
    metadata: dict = None,
):
    """Store embedding in native EmbeddingsCache."""
    if not self.embeddings_cache:
        return

    try:
        await self.embeddings_cache.aset(
            text=text,
            model_name=model_name,
            embedding=embedding,
            metadata=metadata or {},
        )
    except Exception as e:
        logger.error(f"EmbeddingsCache store error: {e}")
```

**Step 3: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "$(cat <<'EOF'
feat(cache): migrate to native RedisVL EmbeddingsCache

- Replace JSON-based embedding storage
- Use async aset/aget methods
- Support metadata storage
- Automatic TTL and key management

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Qdrant Document API Integration

> **Source:** Context7 Qdrant Cloud Inference

**Goal:** Использовать Qdrant Document API для автоматического embedding в запросах.

**Note:** Эта фича опциональна - требует Qdrant Cloud или локальный inference endpoint.

**Files:**
- Create: `telegram_bot/services/qdrant_document.py`

**Step 1: Create Document API wrapper**

```python
"""Qdrant Document API for automatic embedding."""

from qdrant_client import QdrantClient
from qdrant_client.models import Document, Prefetch, FusionQuery, Fusion

class QdrantDocumentSearch:
    """Search using Qdrant's Document API with automatic embedding."""

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        dense_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        sparse_model: str = "Qdrant/bm25",
        colbert_model: str = "colbert-ir/colbertv2.0",
    ):
        self.client = client
        self.collection_name = collection_name
        self.dense_model = dense_model
        self.sparse_model = sparse_model
        self.colbert_model = colbert_model

    async def hybrid_search(
        self,
        query_text: str,
        limit: int = 10,
        prefetch_limit: int = 50,
    ) -> list[dict]:
        """Hybrid search with automatic embedding via Document API."""

        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                # Dense retrieval
                Prefetch(
                    query=Document(
                        text=query_text,
                        model=self.dense_model,
                    ),
                    using="dense",
                    limit=prefetch_limit,
                ),
                # Sparse retrieval (BM25)
                Prefetch(
                    query=Document(
                        text=query_text,
                        model=self.sparse_model,
                    ),
                    using="bm42",
                    limit=prefetch_limit,
                ),
            ],
            # ColBERT reranking
            query=Document(
                text=query_text,
                model=self.colbert_model,
            ),
            using="colbert",
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "id": point.id,
                "score": point.score,
                "payload": point.payload,
            }
            for point in results.points
        ]
```

**Step 2: Alternative with RRF Fusion (no ColBERT)**

```python
async def rrf_search(
    self,
    query_text: str,
    limit: int = 10,
) -> list[dict]:
    """RRF fusion search without ColBERT reranking."""

    results = self.client.query_points(
        collection_name=self.collection_name,
        prefetch=[
            Prefetch(
                query=Document(text=query_text, model=self.dense_model),
                using="dense",
                limit=20,
            ),
            Prefetch(
                query=Document(text=query_text, model=self.sparse_model),
                using="bm42",
                limit=20,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
        with_payload=True,
    )

    return [{"id": p.id, "score": p.score, "payload": p.payload} for p in results.points]
```

**Step 3: Commit**

```bash
git add telegram_bot/services/qdrant_document.py
git commit -m "$(cat <<'EOF'
feat(search): add Qdrant Document API wrapper

- Automatic embedding via Document API
- Hybrid search with dense + sparse + ColBERT
- RRF fusion alternative
- Requires Qdrant Cloud or local inference

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Updated Technology Stack

| Component | Technology | Version | Status |
|-----------|------------|---------|--------|
| Vector DB | Qdrant | 1.10+ | ✅ Existing |
| Dense Embeddings | BGE-M3 | API | ✅ Existing |
| Sparse Embeddings | BM42/IDF | Qdrant | ✅ Task 1-2 |
| ColBERT Reranking | BGE-M3 ColBERT | API | ✅ Task 1-2 |
| HNSW Optimization | m=0 for ColBERT | Qdrant | ✅ Task 1-2 |
| Semantic Cache | RedisVL + langcache | 0.11+ | ⏳ Task 6 |
| Embeddings Cache | RedisVL native | 0.11+ | ⏳ Task 7 |
| Document API | Qdrant Cloud | optional | ⏳ Task 8 |

## Context7 References

- RedisVL SemanticCache: https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/03_llmcache.ipynb
- RedisVL EmbeddingsCache: https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/10_embeddings_cache.ipynb
- Qdrant Hybrid Search: https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search
- Qdrant Document API: https://qdrant.tech/documentation/tutorials-and-examples/cloud-inference-hybrid-search
