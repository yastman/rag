# Project Stack & Architecture

> **Contextual RAG Pipeline** — Production RAG system with hybrid search, local BGE-M3 embeddings, multi-level caching, Telegram bot, voice agent, and comprehensive observability.

**Runtime:** Python 3.12 | ~25,100 LOC | WSL2 (dev) | VPS k3s (prod)

**Use cases:** Bulgarian property (192 docs), Ukrainian Criminal Code (1,294 docs)

---

## Tech Stack

### Core

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12 | Runtime (all services) |
| uv | 0.9–0.10 | Package manager (replaced pip) |
| LangGraph | >=1.0.3 | 10-node StateGraph orchestrator |
| langchain-core | >=1.2 | Core abstractions |
| FastAPI | >=0.115.0 | RAG API (voice) |
| aiogram | >=3.22.0 | Telegram bot framework |
| uvloop | >=0.21.0 | 2–4x faster asyncio |
| tenacity | >=8.2.0 | Retry logic |

### ML & Embeddings

| Technology | Version | Purpose |
|------------|---------|---------|
| BGE-M3 (local) | — | Dense (1024-dim) + sparse + ColBERT rerank |
| sentence-transformers | latest | BGE-M3 model loading |
| FlagEmbedding | latest | BGE-M3 support |
| PyTorch | >=2.0.0 | CPU-only inference |
| transformers | >=4.30.0 | HuggingFace tokenizers |
| voyageai | >=0.3.0 | Voyage embeddings (dev fallback) |
| deepvk/USER2-base | — | Russian semantic cache embeddings |

### LLM

| Technology | Version | Purpose |
|------------|---------|---------|
| LiteLLM | v1.81.3 | LLM gateway (Cerebras/Groq/OpenAI fallback) |
| gpt-oss-120b | — | Primary LLM (Cerebras) |
| Whisper | — | STT via LiteLLM |
| anthropic | latest | Claude API |
| openai | latest | OpenAI/Whisper |

### Database & Cache

| Technology | Version | Purpose |
|------------|---------|---------|
| Qdrant | v1.16 | Vector DB (gRPC + HTTP, hybrid search) |
| Redis | 8.4.0 | 6-tier cache (volatile-lfu, 512MB, `REDIS_PASSWORD` required) |
| PostgreSQL | 17 (pgvector) | Langfuse, MLflow, CocoIndex state, transcripts |
| redisvl | >=0.13.2 | Semantic cache (RedisVL) |

### Voice

| Technology | Version | Purpose |
|------------|---------|---------|
| LiveKit Agents | ~1.3 | Real-time voice framework |
| LiveKit Server | v1.8 | WebRTC media server |
| ElevenLabs | — | STT (Scribe v2, ~80ms) + TTS (Flash v2.5, ~75ms) |
| SIP (lifecell) | — | Outbound calls via lifecell trunk |

### Observability

| Technology | Version | Purpose |
|------------|---------|---------|
| Langfuse | 3.150.0 | LLM observability (35 spans, 14 scores) |
| Loki | 3.4.2 | Log aggregation + alerting rules |
| Promtail | 3.4.2 | Docker log collection |
| Alertmanager | v0.28.1 | Alert routing to Telegram |
| MLflow | >=3.9.0 | Experiment tracking |
| RAGAS | >=0.4.3 | RAG evaluation (faithfulness >= 0.8) |

### Ingestion

| Technology | Version | Purpose |
|------------|---------|---------|
| CocoIndex | >=0.3.28 (v3.2.1) | Unified ingestion framework |
| Docling | >=2.70.0 | PDF/DOCX/CSV parsing + chunking |
| pymupdf | >=1.26.0 | PDF extraction |

### Dev Tools

| Technology | Version | Purpose |
|------------|---------|---------|
| Ruff | >=0.6.0 | Linter + formatter |
| MyPy | >=1.11.0 | Type checking (strict in CI) |
| pytest | >=8.3.0 | Testing (+ xdist, asyncio, httpx, timeout) |
| pre-commit | >=3.8.0 | Git hooks (ruff, format, yaml/toml/json) |
| bandit | >=1.7.9 | Security scanning |
| Docker Compose v2 | — | Local orchestration (profiles) |
| k3s + Kustomize | — | VPS deployment |
| Mend Renovate | — | Automated dependency updates |

---

## Architecture

### High-Level

```
                    ┌─────────────┐
                    │  Telegram    │
                    │  Bot (aiogram)│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐       ┌──────────────┐
                    │  LangGraph  │◄──────│  RAG API     │◄── Voice Agent
                    │  10-node    │       │  (FastAPI)   │    (LiveKit)
                    │  StateGraph │       └──────────────┘
                    └──────┬──────┘
                           │
          ┌────────┬───────┼───────┬──────────┐
          ▼        ▼       ▼       ▼          ▼
       ┌──────┐ ┌─────┐ ┌─────┐ ┌────────┐ ┌────────┐
       │Redis │ │Qdrant│ │BGE-M3│ │LiteLLM │ │Langfuse│
       │6-tier│ │gRPC  │ │local │ │gateway │ │v3      │
       │cache │ │hybrid│ │embed │ │LLM     │ │observe │
       └──────┘ └─────┘ └─────┘ └────────┘ └────────┘
```

### Module Map

```
telegram_bot/                      # Bot + LangGraph pipeline (17,300 LOC)
├── bot.py                         # PropertyBot (~300 LOC, orchestrator + score writer)
├── config.py                      # BotConfig (pydantic-settings)
├── observability.py               # Langfuse init, @observe, PII masking
├── preflight.py                   # Health checks (Redis, Qdrant, BGE-M3, LiteLLM)
├── graph/                         # LangGraph StateGraph
│   ├── graph.py                   # build_graph() — assembles 10 nodes
│   ├── state.py                   # RAGState TypedDict (25 fields)
│   ├── edges.py                   # 4 routing functions
│   ├── config.py                  # GraphConfig (factories, thresholds)
│   └── nodes/                     # 10 nodes (transcribe→classify→cache→retrieve→
│       └── ...                    #   grade→rerank→generate→rewrite→cache_store→respond)
├── services/                      # Business logic
│   ├── qdrant.py                  # QdrantService (gRPC, batch_search_rrf, group_by)
│   ├── colbert_reranker.py        # ColBERT via BGE-M3 /rerank
│   ├── llm.py                     # LLMService (langfuse.openai.AsyncOpenAI)
│   └── vectorizers.py             # UserBase + BgeM3 vectorizers
├── integrations/                  # LangGraph wrappers
│   ├── cache.py                   # CacheLayerManager (6-tier, ~430 LOC)
│   ├── embeddings.py              # BGEM3HybridEmbeddings (1-call dense+sparse)
│   ├── prompt_manager.py          # Langfuse prompt management
│   └── memory.py                  # Conversation persistence
└── middlewares/                   # Rate limiting, error handling

src/                               # Core services (7,800 LOC)
├── ingestion/unified/             # CocoIndex v3.2.1 pipeline
│   ├── flow.py                    # CocoIndex flow, manifest-based file_id
│   ├── cli.py                     # CLI: preflight, bootstrap, run, status
│   ├── qdrant_writer.py           # Sync upsert/delete to Qdrant
│   ├── state_manager.py           # Postgres state + DLQ
│   └── manifest.py                # Content-hash → stable UUID
├── api/                           # FastAPI RAG API (POST /query)
├── voice/                         # LiveKit voice agent
│   ├── agent.py                   # VoiceBot + AgentServer
│   ├── transcript_store.py        # PostgreSQL async (asyncpg)
│   └── sip_setup.py               # lifecell SIP trunk
├── retrieval/                     # Search engine variants (evaluation)
└── evaluation/                    # RAGAS + baseline metrics
```

---

## Pipelines

### 1. Ingestion Pipeline

```
Google Drive → rclone sync → local files
                                │
                    ┌───────────▼────────────┐
                    │  CocoIndex Flow         │
                    │  (FlowLiveUpdater)      │
                    │                         │
                    │  LocalFile source        │
                    │  ↓ 60s refresh          │
                    │  Manifest (SHA256→UUID) │
                    │  ↓                      │
                    │  Docling parsing        │
                    │  (speed/quality/scan)   │
                    │  ↓                      │
                    │  BGE-M3 embeddings      │
                    │  dense 1024 + sparse    │
                    │  ↓                      │
                    │  Qdrant upsert (sync)   │
                    │  ↓                      │
                    │  Postgres state + DLQ   │
                    └─────────────────────────┘
```

**Key details:**
- All operations are **sync** (CocoIndex `mutate()` requirement)
- Manifest: content-hash → stable UUID (rename/move safe, no duplicates)
- Collections: `gdrive_documents_bge` (VPS), `legal_documents` (dev)

### 2. Query Pipeline (LangGraph 10 nodes)

```
START
  │
  ├─ voice_audio? ──YES──► transcribe (Whisper STT)
  │                              │
  └─ NO ─────────────────────────┤
                                 ▼
                            classify (regex: CHITCHAT/GENERAL/STRUCTURED)
                                 │
                    ┌────────────┴────────────┐
                    │                         │
               CHITCHAT/OFF_TOPIC        GENERAL/STRUCTURED
                    │                         │
                    ▼                         ▼
                 respond              cache_check
                    │              (embed hybrid 1-call + semantic cache)
                    ▼                         │
                   END               ┌────────┴────────┐
                                     │                  │
                                  HIT/ERROR          MISS
                                     │                  │
                                     ▼                  ▼
                                  respond           retrieve
                                     │          (RRF: dense 0.6 + sparse 0.4)
                                     ▼                  │
                                    END                 ▼
                                                     grade
                                                  (threshold 0.005)
                                                        │
                                        ┌───────────────┼───────────┐
                                        │               │           │
                                    relevant        relevant    not relevant
                                  conf >= 0.012   conf < 0.012      │
                                        │               │       rewrite_count
                                        │               │       < max?
                                        │               ▼           │
                                        │           rerank      ┌───┴───┐
                                        │          (ColBERT)    YES    NO
                                        │               │       │      │
                                        ▼               ▼       ▼      ▼
                                      generate ◄────────┘   rewrite  generate
                                        │                      │    (fallback)
                                        ▼                      │
                                   cache_store                 ▼
                                        │                  retrieve
                                        ▼                  (loop)
                                     respond
                                        │
                                        ▼
                                       END
```

**RAGState:** 25 fields (messages, embeddings, documents, scores, latency_stages, voice metadata)

### 3. Search & Retrieval

```
Query → BGE-M3 /encode/hybrid (1 call)
           ├── Dense vector (1024-dim)
           └── Sparse vector (lexical_weights)
                    │
                    ▼
           Qdrant Prefetch
           ├── Dense HNSW search
           └── Sparse inverted index
                    │
                    ▼
           RRF Fusion (k=60)
           score = 0.6/(k + dense_rank) + 0.4/(k + sparse_rank)
                    │
                    ▼
           Grade (threshold 0.005)
                    │
           ┌────────┴────────┐
           │                 │
      confidence >= 0.012  < 0.012
           │                 │
      skip rerank       ColBERT rerank
           │            (BGE-M3 /rerank,
           │             MaxSim, top-5)
           └────────┬────────┘
                    ▼
                 Results
```

| Engine Variant | Recall@1 | Latency | Description |
|----------------|----------|---------|-------------|
| HybridRRF+ColBERT | 94% | ~1.0s | **Default** |
| HybridRRF | 92% | ~0.8s | Without rerank |
| DBSFColBERT | 91% | ~0.7s | Faster fusion |
| Dense-only | 91.3% | ~0.65s | Baseline |

### 4. Voice Pipeline

```
Telegram /call
     │
     ▼
LiveKit API (dispatch + SIP)
     │
     ▼
lifecell SIP trunk ◄──► LiveKit SIP Server
                              │
                              ▼
                    LiveKit Voice Agent
                    ├── ElevenLabs Scribe v2 (STT, ~80ms)
                    ├── LLM via LiteLLM (gpt-4o-mini)
                    ├── @function_tool → RAG API (POST /query)
                    ├── ElevenLabs Flash v2.5 (TTS, ~75ms)
                    └── Langfuse via OTEL
                              │
                              ▼
                    PostgreSQL (call transcripts)
```

**Decoupled architecture:** Voice agent communicates with RAG via HTTP (FastAPI), not direct import.

---

## Caching (6-tier)

```
CacheLayerManager (telegram_bot/integrations/cache.py, ~430 LOC)

┌─────────────────────────────────────────────────┐
│ Tier 1: Semantic Cache (RedisVL)                │
│   STRUCTURED: threshold 0.05, TTL 2h            │
│   GENERAL:    threshold 0.08, TTL 1h            │
│   ENTITY:     threshold 0.10, TTL 1h            │
│   FAQ:        threshold 0.12, TTL 24h           │
├─────────────────────────────────────────────────┤
│ Tier 2: Embeddings Cache (exact, 7d TTL)        │
│ Tier 3: Sparse Embeddings Cache (exact, 7d TTL) │
│ Tier 4: Analysis Cache (exact, 24h TTL)         │
│ Tier 5: Search Results Cache (exact, 2h TTL)    │
│ Tier 6: Rerank Results Cache (exact, 2h TTL)    │
├─────────────────────────────────────────────────┤
│ + Conversation History (LIST, 20 msgs, 2h TTL)  │
│   Stored via Redis pipelines (1 round-trip)     │
└─────────────────────────────────────────────────┘
```

Lower semantic threshold = stricter matching (closer vectors required for cache hit).

---

## Observability

### Langfuse v3 Instrumentation

| Category | Count | Details |
|----------|-------|---------|
| Graph nodes | 10 | `@observe(name="node-*")`, 6 heavy with curated spans |
| Cache methods | 9 | semantic-check, semantic-store, exact-get, etc. |
| Embedding calls | 3 | hybrid-embed, dense-embed, sparse-embed |
| Service calls | 3 | colbert-rerank, qdrant-hybrid-search-rrf, batch-search |
| LLM calls | 5 | generate-answer, stream-answer, query-analysis, hyde, rewrite |
| Voyage calls | 5 | embed-query, embed-docs, rerank, etc. |
| **Total** | **35** | per trace |

### Scores Written Per Trace (14+)

| Score | Type | Source |
|-------|------|--------|
| query_type | CATEGORICAL | classify node |
| latency_total_ms | NUMERIC | bot.py |
| semantic_cache_hit | BOOLEAN | cache_check |
| embeddings_cache_hit | BOOLEAN | cache_check |
| search_cache_hit | BOOLEAN | retrieve |
| rerank_applied | BOOLEAN | rerank |
| results_count | NUMERIC | retrieve |
| no_results | BOOLEAN | grade |
| llm_used | BOOLEAN | generate |
| confidence_score | NUMERIC | grade |
| llm_ttft_ms | NUMERIC | generate |
| answer_words | NUMERIC | bot.py |
| input_type | CATEGORICAL | voice |
| stt_duration_ms | NUMERIC | voice |

### Error Tracking

4 nodes emit `level=ERROR` spans: generate, rewrite, rerank, respond.

### Orphan Prevention

```python
with traced_pipeline(session_id="chat-{hash}-{YYYYMMDD}", user_id="123"):
    result = await graph.ainvoke(state)
```

Without `traced_pipeline`, each `@observe` creates a separate root trace.

---

## Infrastructure

### Docker Profiles

| Profile | Services | Startup | Use Case |
|---------|----------|---------|----------|
| `core` | postgres, redis, qdrant, docling, bm42 | ~17s | Minimum viable |
| `bot` | core + litellm, bot | 2–3 min | Bot development |
| `ai` | core + bge-m3, user-base, lightrag | — | Heavy ML models |
| `ml` | core + langfuse, clickhouse, minio, mlflow | — | ML platform |
| `obs` | core + loki, promtail, alertmanager | — | Monitoring |
| `ingest` | core + ingestion | — | Document ingestion |
| `voice` | core + rag-api, livekit, sip, voice-agent | — | Voice calls |
| `full` | all 16+ services | ~5 min | Everything |

### VPS Deployment (k3s)

**Server:** `admin@95.111.252.29:1654` | 11GB RAM

| Service | Memory Limit | Notes |
|---------|-------------|-------|
| bge-m3 | 4GB | Largest service |
| user-base | 2GB | Russian embeddings |
| qdrant | 1GB | Vector DB |
| postgres | 512MB | State |
| redis | 300MB | Cache |
| litellm | 512MB | LLM gateway |
| bot | 512MB | Telegram bot |
| k3s overhead | ~1.6GB | System |

**k3s overlays:** core (11 resources) → bot (19) → ingest (17) → full (23)

**Redis auth:** All profiles (local, VPS, k3s) require `REDIS_PASSWORD`. Redis runs with `--requirepass`, app services use `REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379`.

### Monitoring Stack

```
Docker containers → Promtail → Loki (Ruler) → Alertmanager → Telegram
```

---

## Features

### Shipped

| Feature | Issues | Description |
|---------|--------|-------------|
| Hybrid RRF Search | — | Dense + sparse + ColBERT rerank, 94% recall |
| 6-tier Caching | — | Semantic + exact Redis cache with query-type thresholds |
| Voice Bot | #153, #151 | LiveKit Agent + ElevenLabs + lifecell SIP |
| Conversation Memory | #154, #152 | Redis checkpointer, short-term context |
| Observability | #159, #158 | 35 spans, 14 scores, error tracking |
| Streaming | — | LLM streaming to Telegram with fallback |
| Semantic Cache Isolation | #163 | Per-user cache with query-type thresholds |
| HyDE | — | Hypothetical document generation |
| Query Classification | — | Regex CHITCHAT/GENERAL/STRUCTURED routing |
| Unified Ingestion | — | CocoIndex v3.2.1 with manifest dedup |
| Monitoring & Alerting | — | Loki + Alertmanager → Telegram |
| k3s Deployment | — | Kustomize overlays, VPS |
| Baseline Comparison | #167 | Langfuse session-based A/B testing |
| BGE-M3 Hybrid 1-call | — | /encode/hybrid returns dense + sparse |

### In Progress / Next (P1)

| Issue | Title |
|-------|-------|
| #222 | Conversational/memory questions bypass retrieval |
| #221 | xdist leak in generate_node prompt source |
| #217 | 37% voice traces missing Langfuse scores |
| #216 | 164 unit test failures (mock/async compat) |
| #215 | **P0** Ingestion read-only filesystem blocker |
| #214 | PoolTimeout in retryable errors |
| #213 | PropertyBot timeout regression |

### Backlog Highlights (P2)

| Issue | Title |
|-------|-------|
| #133 | Kommo CRM integration epic |
| #137 | LiteLLM tool-calling ReAct loop |
| #140 | 3-tier memory (Redis + Kommo + Qdrant) |
| #142 | Multi-agent handoff protocol |
| #147 | Latency breakdown (queue, TTFT, decode) |
| #106 | BGE-M3 ONNX backend |
| #127 | LLM-as-a-Judge calibration |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Local BGE-M3** (no API) | Zero cost, full control, CPU inference viable |
| **Hybrid 1-call** (`/encode/hybrid`) | 50% fewer HTTP calls vs separate dense+sparse |
| **RRF over DBSF** | +3% recall, configurable weights (0.6/0.4) |
| **ColBERT rerank conditional** | Skip when confidence >= 0.012 (saves ~200ms) |
| **Sync ingestion** | CocoIndex requires sync `mutate()`, no `asyncio.run()` |
| **Manifest dedup** | Content-hash → UUID prevents duplicates on rename/move |
| **Curated Langfuse spans** | `capture_input/output=False` on 6 heavy nodes (payload bloat) |
| **Redis pipelines** | 1 round-trip for conversation store (rpush + ltrim + expire) |
| **Decoupled voice** | HTTP to RAG API, no shared imports with bot |
| **Graceful degradation** | No reranker → score-sort; LLM fail → doc summary; no Langfuse → no-op |

---

## Python Dependencies (87 packages)

<details>
<summary>Full list grouped by category</summary>

### Core (8)
python-dotenv, uvloop, aiohttp, requests, httpx, tenacity, asyncpg, pydantic

### ML & Embeddings (7)
torch (CPU), torchvision, sentence-transformers, FlagEmbedding, transformers, scipy, numpy

### LLM (4)
anthropic, openai, groq, voyageai

### Document Processing (4)
pymupdf, docling, docling-core, cocoindex

### Database & Cache (4)
qdrant-client, fastembed, redis, redisvl

### LangGraph (5)
langgraph, langchain-core, langgraph-checkpoint-postgres, langgraph-checkpoint-redis, langmem

### Observability (4)
langfuse, mlflow, ragas, datasets

### Bot (2)
aiogram, pandas

### Voice (8)
livekit-agents, livekit-plugins-elevenlabs, livekit-plugins-openai, livekit, fastapi, uvicorn, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http

### Dev (17)
ruff, mypy, pylint, bandit, vulture, pytest, pytest-cov, pytest-asyncio, pytest-httpx, pytest-timeout, pytest-xdist, opentelemetry-exporter-otlp-proto-grpc, pre-commit, telethon, mkdocs, mkdocs-material, mkdocstrings

</details>

---

## Quick Commands

```bash
# Development
uv sync                              # Install deps
make check                           # Lint + types
make test-unit                       # Unit tests
uv run pytest tests/unit/ -n auto    # Parallel tests (~5 min)

# Docker
make docker-core-up                  # 5 services, ~17s
make docker-bot-up                   # + bot
make docker-full-up                  # All 16+ services

# Evaluation
make eval-rag                        # RAGAS faithfulness >= 0.8
make validate-traces-fast            # Trace validation

# Deployment
make k3s-bot                         # Deploy to VPS
make k3s-status                      # Check pods

# Monitoring
make monitoring-up                   # Loki + Alertmanager
make monitoring-test-alert           # Test Telegram alert
```

---

## Project Stats

| Metric | Value |
|--------|-------|
| Total LOC | ~25,100 |
| Python packages | 87 (main + dev + voice + docs) |
| Docker services | 16+ (6 profiles) |
| Custom Dockerfiles | 8 |
| LangGraph nodes | 10 |
| Langfuse spans/trace | 35 |
| Langfuse scores/trace | 14+ |
| Cache tiers | 6 + conversation |
| GitHub issues | 222 (212 closed, 10 open) |
| Qdrant collections | 4 |
| Makefile targets | 70+ |
| k3s resources | 23 (full overlay) |
