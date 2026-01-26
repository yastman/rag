# Docling → Qdrant → n8n (BGE-M3) — Task Checklist (Updated 2025-10-22 06:41:41)

Goal: Build a production pipeline from Docling structure extraction to hybrid search in Qdrant with reranking and orchestration through n8n/Redis. Output: ready-to-use steps on what to configure and how.

---

## 0) Prerequisites and Versions
1. Server: 6 CPU / 12 GB RAM / SSD (or equivalent).
2. Containers/services:
   - Docling (CLI/library) and/or Docling Serve (if REST needed).
   - Qdrant ≥ 1.15.x.
   - Embeddings API: BGE-M3 (dense + sparse + colbert).
   - Redis 8.2.x.
   - n8n (orchestration).
3. Python ≥ 3.10 for processing scripts.

See architectural plan and collection parameters, caching and metrics: `RAG_ARCHITECTURE_BLUEPRINT_v3.md`, `RAG_DEPLOYMENT_PLAN_UPDATED_2025.md`, `rag_contextual_improvements_v_2025.md`, `rag_qdrant_n_8_n_plan_v_2025.md` (these files are already in your repository).

---

## 1) Converting Documents to DoclingDocument
Task: Obtain a unified `DoclingDocument` object with text, tables, images, hierarchy and metadata.
- Install docling:
  ```bash
  pip install -U docling docling-core[chunking]
  ```
- Conversion:
  ```python
  from docling.document_converter import DocumentConverter
  dl_doc = DocumentConverter().convert(source=PATH_OR_URL).document
  ```
- Verify presence of structural nodes (`body`, `groups`, headings), tables, images.

Result: Correctly formed `DoclingDocument`, suitable for chunking/serialization.

---

## 2) Chunking: Hierarchical → Hybrid
Task: Split document into meaningful fragments, considering structure and token limits.
- Basic path: Start with `HierarchicalChunker` (chunk per structure element; can attach headers/captions).
- Then apply `HybridChunker` with tokenizer **aligned with embedding model** (e.g., HF-tokenizer for BGE-M3). Configure:
  - Target chunk size: 1200-2000 characters (or 400-800 tokens).
  - Overlap: 10-15%.
  - `merge_peers=True` (default) - merge underloaded neighboring chunks with same headers.
- During `contextualize(chunk)` stage, add prefix with section/subsection title.

Result: Stream of chunks with rich structure and context, ready for serialization/embeddings.

---

## 3) Serialization (Markdown/JSON/YAML) + DPK (optional)
Task: Save text and metadata for audit and subsequent ingest.
- Basic serialization (example): `MarkdownDocSerializer` or `HTMLDocSerializer` for human-readable audit + JSON/YAML for machine processing.
- Mini-normalization of text before embedding: Unicode NFC, remove `\u00AD`, join lines without trailing punctuation.
- Option: Data Prep Kit (DPK) pipeline, if standardized conveyor needed:
  - `Docling2Parquet` → `Doc_Chunk` → `Tokenization` (align tokenizer model with embedder).
  - Output: parquet files at each stage; convenient for debugging.

Result: Token-friendly chunks with explicit metadata and reproducible serialization.

---

## 4) Embeddings (BGE-M3: dense + sparse + colbert/multivector)
Task: Get three representations from each chunk.
- For each chunk, form input as: `"{section_title}: {chunk_text}"`.
- Call encode with return: dense (1024-D), sparse (lexical weights), colbert vectors (multivector).
- Save resulting vectors alongside payload (see metadata schema below).

Result: Three types of embeddings for hybrid prefetch and late-interaction rerank.

---

## 5) Qdrant: Collection and Loading
Task: Create collection with three types of representations and CPU optimizations.
- Collection:
  - `vectors.dense` size=1024, distance=Cosine, **quantization=int8** (after A/B test).
  - `vectors.colbert` size=1024, multivector=MaxSim, **no HNSW** (used only as rerank).
  - `sparse_vectors.sparse` enabled.
  - HNSW: m=16, ef_construct=100, ef_search=64 (for dense).
  - Text index/tokenizer: multilingual (if database is Ukrainian/Russian).
- Payload/metadata (example):
  ```json
  {
    "document_id": "...",
    "language": "uk",
    "source": "CK.pdf",
    "book": "...", "chapter": "...",
    "article_no": "25",
    "section_title": "...",
    "page_start": 5, "page_end": 7,
    "element_type": "article|section|table",
    "prev_section": "...", "next_section": "...",
    "date": "2024-01-01"
  }
  ```
- Upsert: Write `dense`, `sparse`, `colbert` + payload.

Result: Collection ready for hybrid search with late rerank.

---

## 6) Search Query (retrieve → rerank) + Filters
Task: Make one call to Qdrant with prefetch phase and final rerank.
- Prefetch:
  - dense limit=50-100
  - sparse limit=30-50
  - fusion: DBSF or RRF (DBSF recommended as primary).
- Rerank: `using="colbert"`, limit=10.
- Filters: `lang="uk"`, by dates/source when necessary.
- Dedup: Keep no more than 1-2 chunks per `article_no`/`document_id`.
- Filter low scores; if context insufficient - fetch neighboring chunks (`prev_section`/`next_section`).

Result: Robust hybrid retrieve with precise rerank and context sufficiency control.

---

## 7) n8n Orchestration and Redis Cache
Task: Assemble end-to-end workflow and reduce load.
- n8n (typical graph):
  `Webhook → HTTP(Embed API: BGE-M3) → HTTP(Qdrant query) → Function(dedup/join/length control) → HTTP(LLM) → Respond → Redis.set`
- Redis 8.2.x:
  - L2: query embedding cache (TTL 24h).
  - L3: search results cache (TTL 7-12h).
  - Policy: `allkeys-lru`, memory limit 1-2 GB.
- Fusion weight profiles: general 0.7/0.3; legal 0.55/0.45; mixed-lang 0.65/0.35.

Result: Fast responses, less load on embedder/Qdrant/LLM.

---

## 8) Contextualization and Retrieval Improvements
Task: Increase relevance without cost increase.
- Contextual Chunking: section prefixes + overlap.
- Query Expansion (Function/LLM node): synonyms/term variants for Ukrainian/Russian.
- Context-aware rerank: +0.1 to score for same `document_id`, +0.05 for sections like "Conclusions".
- Sufficiency control: minimum 2 documents in context or expand top-N and add neighbors.

Result: Recall/NDCG increase, hallucinations decrease.

---

## 9) Quality Evaluation (offline)
Task: Record metrics before/after tuning.
- Set of 30+ queries (specify expected articles/sections).
- Metrics: Recall@K, NDCG@K, MRR, Faithfulness, Answer Relevance.
- Baseline vs changes (quantization, ef_search, prefetch limits, etc.).
- Acceptance criteria: quality not degraded (thresholds from blueprint).

Result: Controlled tuning without regressions.

---

## 10) Observability and Alerts
Task: See latencies/errors/cache effectiveness.
- Prometheus exports:
  - `rag_chunking_duration_seconds`, `rag_embedding_latency_seconds`, `rag_search_latency_seconds`.
  - `rag_cache_hits_total/misses_total` and hit-ratio by L2/L3.
  - `rag_errors_total{stage="chunking|embedding|search|insert"}`.
- Grafana panels: latency p50/p95/p99, hit-ratio, errors, throughput.
- Alerts: p95 > 0.5-1.0s; errors > 1%; hit-ratio drop.

Result: Transparency of operation and quick response to degradations.

---

## 11) Security and Limits
- Limits on PDF size (≤ 50 MB) and page count (≤ 2000).
- Redis ACL, Qdrant API keys, container CPU/RAM limits.
- Logs (PII/secrets) not included in payload/context.

---

## 12) Final Check (go-live checklist)
- [ ] Qdrant collection created (dense+sparse+colbert), quantization tested.
- [ ] Chunking produces ≥ 50 chunks/document, coverage ≥ 70% of content.
- [ ] Embeddings and ingest pipeline complete without errors, validation passed.
- [ ] Search: prefetch+fusion works, colbert rerank delivers stable top-10.
- [ ] n8n: Redis cache enabled, weight profiles configured.
- [ ] Quality evaluation completed; metrics meet goals.
- [ ] Metrics/alerts in Grafana/Prometheus active.
- [ ] Documentation and query examples updated.

---

## Implementation Notes
- Context-dependent text representation for embeddings ("`Section: ...` + text") increases Recall/NDCG.
- For legal documents, multilingual tokenization (Ukrainian/Russian) and sparse signal (BM25-like) are critical.
- Multivector rerank in Qdrant removes need for heavy cross-encoder on CPU.
