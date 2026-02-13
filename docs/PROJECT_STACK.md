***REMOVED*** Project Stack & Architecture

> **Contextual RAG Pipeline** — Production RAG system with hybrid search, local BGE-M3 embeddings, multi-level caching, Telegram bot, voice agent, and comprehensive observability.

**Runtime:** Python 3.12 | ~25,100 LOC | WSL2 (dev) | VPS k3s (prod)

**Use cases:** Bulgarian property (192 docs), Ukrainian Criminal Code (1,294 docs)

---

***REMOVED******REMOVED*** Tech Stack

***REMOVED******REMOVED******REMOVED*** Core

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

***REMOVED******REMOVED******REMOVED*** ML & Embeddings

| Technology | Version | Purpose |
|------------|---------|---------|
| BGE-M3 (local) | — | Dense (1024-dim) + sparse + ColBERT rerank |
| sentence-transformers | latest | BGE-M3 model loading |
| FlagEmbedding | latest | BGE-M3 support |
| PyTorch | >=2.0.0 | CPU-only inference |
| transformers | >=4.30.0 | HuggingFace tokenizers |
| voyageai | >=0.3.0 | Voyage embeddings (dev fallback) |
| deepvk/USER2-base | — | Russian semantic cache embeddings |

***REMOVED******REMOVED******REMOVED*** LLM

| Technology | Version | Purpose |
|------------|---------|---------|
| LiteLLM | v1.81.3 | LLM gateway (Cerebras/Groq/OpenAI fallback) |
| gpt-oss-120b | — | Primary LLM (Cerebras) |
| Whisper | — | STT via LiteLLM |
| anthropic | latest | Claude API |
| openai | latest | OpenAI/Whisper |

***REMOVED******REMOVED******REMOVED*** Database & Cache

| Technology | Version | Purpose |
|------------|---------|---------|
| Qdrant | v1.16 | Vector DB (gRPC + HTTP, hybrid search) |
| Redis | 8.4.0 | 6-tier cache (volatile-lfu, 512MB) |
| PostgreSQL | 17 (pgvector) | Langfuse, MLflow, CocoIndex state, transcripts |
| redisvl | >=0.13.2 | Semantic cache (RedisVL) |

***REMOVED******REMOVED******REMOVED*** Voice

| Technology | Version | Purpose |
|------------|---------|---------|
| LiveKit Agents | ~1.3 | Real-time voice framework |
| LiveKit Server | v1.8 | WebRTC media server |
| ElevenLabs | — | STT (Scribe v2, ~80ms) + TTS (Flash v2.5, ~75ms) |
| SIP (lifecell) | — | Outbound calls via lifecell trunk |

***REMOVED******REMOVED******REMOVED*** Observability

| Technology | Version | Purpose |
|------------|---------|---------|
| Langfuse | 3.150.0 | LLM observability (35 spans, 14 scores) |
| Loki | 3.4.2 | Log aggregation + alerting rules |
| Promtail | 3.4.2 | Docker log collection |
| Alertmanager | v0.28.1 | Alert routing to Telegram |
| MLflow | >=3.9.0 | Experiment tracking |
| RAGAS | >=0.4.3 | RAG evaluation (faithfulness >= 0.8) |

***REMOVED******REMOVED******REMOVED*** Ingestion

| Technology | Version | Purpose |
|------------|---------|---------|
| CocoIndex | >=0.3.28 (v3.2.1) | Unified ingestion framework |
| Docling | >=2.70.0 | PDF/DOCX/CSV parsing + chunking |
| pymupdf | >=1.26.0 | PDF extraction |

***REMOVED******REMOVED******REMOVED*** Dev Tools

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

***REMOVED******REMOVED*** Architecture

***REMOVED******REMOVED******REMOVED*** High-Level

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

***REMOVED******REMOVED******REMOVED*** Module Map

```
telegram_bot/                      ***REMOVED*** Bot + LangGraph pipeline (17,300 LOC)
├── bot.py                         ***REMOVED*** PropertyBot (~300 LOC, orchestrator + score writer)
├── config.py                      ***REMOVED*** BotConfig (pydantic-settings)
├── observability.py               ***REMOVED*** Langfuse init, @observe, PII masking
├── preflight.py                   ***REMOVED*** Health checks (Redis, Qdrant, BGE-M3, LiteLLM)
├── graph/                         ***REMOVED*** LangGraph StateGraph
│   ├── graph.py                   ***REMOVED*** build_graph() — assembles 10 nodes
│   ├── state.py                   ***REMOVED*** RAGState TypedDict (25 fields)
│   ├── edges.py                   ***REMOVED*** 4 routing functions
│   ├── config.py                  ***REMOVED*** GraphConfig (factories, thresholds)
│   └── nodes/                     ***REMOVED*** 10 nodes (transcribe→classify→cache→retrieve→
│       └── ...                    ***REMOVED***   grade→rerank→generate→rewrite→cache_store→respond)
├── services/                      ***REMOVED*** Business logic
│   ├── qdrant.py                  ***REMOVED*** QdrantService (gRPC, batch_search_rrf, group_by)
│   ├── colbert_reranker.py        ***REMOVED*** ColBERT via BGE-M3 /rerank
│   ├── llm.py                     ***REMOVED*** LLMService (langfuse.openai.AsyncOpenAI)
│   └── vectorizers.py             ***REMOVED*** UserBase + BgeM3 vectorizers
├── integrations/                  ***REMOVED*** LangGraph wrappers
│   ├── cache.py                   ***REMOVED*** CacheLayerManager (6-tier, ~430 LOC)
│   ├── embeddings.py              ***REMOVED*** BGEM3HybridEmbeddings (1-call dense+sparse)
│   ├── prompt_manager.py          ***REMOVED*** Langfuse prompt management
│   └── memory.py                  ***REMOVED*** Conversation persistence
└── middlewares/                   ***REMOVED*** Rate limiting, error handling

src/                               ***REMOVED*** Core services (7,800 LOC)
├── ingestion/unified/             ***REMOVED*** CocoIndex v3.2.1 pipeline
│   ├── flow.py                    ***REMOVED*** CocoIndex flow, manifest-based file_id
│   ├── cli.py                     ***REMOVED*** CLI: preflight, bootstrap, run, status
│   ├── qdrant_writer.py           ***REMOVED*** Sync upsert/delete to Qdrant
│   ├── state_manager.py           ***REMOVED*** Postgres state + DLQ
│   └── manifest.py                ***REMOVED*** Content-hash → stable UUID
├── api/                           ***REMOVED*** FastAPI RAG API (POST /query)
├── voice/                         ***REMOVED*** LiveKit voice agent
│   ├── agent.py                   ***REMOVED*** VoiceBot + AgentServer
│   ├── transcript_store.py        ***REMOVED*** PostgreSQL async (asyncpg)
│   └── sip_setup.py               ***REMOVED*** lifecell SIP trunk
├── retrieval/                     ***REMOVED*** Search engine variants (evaluation)
└── evaluation/                    ***REMOVED*** RAGAS + baseline metrics
```

---

***REMOVED******REMOVED*** Pipelines

***REMOVED******REMOVED******REMOVED*** 1. Ingestion Pipeline

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

***REMOVED******REMOVED******REMOVED*** 2. Query Pipeline (LangGraph 10 nodes)

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

***REMOVED******REMOVED******REMOVED*** 3. Search & Retrieval

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

***REMOVED******REMOVED******REMOVED*** 4. Voice Pipeline

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

***REMOVED******REMOVED*** Caching (6-tier)

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

***REMOVED******REMOVED*** Observability

***REMOVED******REMOVED******REMOVED*** Langfuse v3 Instrumentation

| Category | Count | Details |
|----------|-------|---------|
| Graph nodes | 10 | `@observe(name="node-*")`, 6 heavy with curated spans |
| Cache methods | 9 | semantic-check, semantic-store, exact-get, etc. |
| Embedding calls | 3 | hybrid-embed, dense-embed, sparse-embed |
| Service calls | 3 | colbert-rerank, qdrant-hybrid-search-rrf, batch-search |
| LLM calls | 5 | generate-answer, stream-answer, query-analysis, hyde, rewrite |
| Voyage calls | 5 | embed-query, embed-docs, rerank, etc. |
| **Total** | **35** | per trace |

***REMOVED******REMOVED******REMOVED*** Scores Written Per Trace (14+)

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

***REMOVED******REMOVED******REMOVED*** Error Tracking

4 nodes emit `level=ERROR` spans: generate, rewrite, rerank, respond.

***REMOVED******REMOVED******REMOVED*** Orphan Prevention

```python
with traced_pipeline(session_id="chat-{hash}-{YYYYMMDD}", user_id="123"):
    result = await graph.ainvoke(state)
```

Without `traced_pipeline`, each `@observe` creates a separate root trace.

---

***REMOVED******REMOVED*** Infrastructure

***REMOVED******REMOVED******REMOVED*** Docker Profiles

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

***REMOVED******REMOVED******REMOVED*** VPS Deployment (k3s)

**Server:** `admin@REDACTED_VPS_ENDPOINT` | 11GB RAM

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

***REMOVED******REMOVED******REMOVED*** Monitoring Stack

```
Docker containers → Promtail → Loki (Ruler) → Alertmanager → Telegram
```

---

***REMOVED******REMOVED*** Features

***REMOVED******REMOVED******REMOVED*** Shipped

| Feature | Issues | Description |
|---------|--------|-------------|
| Hybrid RRF Search | — | Dense + sparse + ColBERT rerank, 94% recall |
| 6-tier Caching | — | Semantic + exact Redis cache with query-type thresholds |
| Voice Bot | ***REMOVED***153, ***REMOVED***151 | LiveKit Agent + ElevenLabs + lifecell SIP |
| Conversation Memory | ***REMOVED***154, ***REMOVED***152 | Redis checkpointer, short-term context |
| Observability | ***REMOVED***159, ***REMOVED***158 | 35 spans, 14 scores, error tracking |
| Streaming | — | LLM streaming to Telegram with fallback |
| Semantic Cache Isolation | ***REMOVED***163 | Per-user cache with query-type thresholds |
| HyDE | — | Hypothetical document generation |
| Query Classification | — | Regex CHITCHAT/GENERAL/STRUCTURED routing |
| Unified Ingestion | — | CocoIndex v3.2.1 with manifest dedup |
| Monitoring & Alerting | — | Loki + Alertmanager → Telegram |
| k3s Deployment | — | Kustomize overlays, VPS |
| Baseline Comparison | ***REMOVED***167 | Langfuse session-based A/B testing |
| BGE-M3 Hybrid 1-call | — | /encode/hybrid returns dense + sparse |

***REMOVED******REMOVED******REMOVED*** In Progress / Next (P1)

| Issue | Title |
|-------|-------|
| ***REMOVED***222 | Conversational/memory questions bypass retrieval |
| ***REMOVED***221 | xdist leak in generate_node prompt source |
| ***REMOVED***217 | 37% voice traces missing Langfuse scores |
| ***REMOVED***216 | 164 unit test failures (mock/async compat) |
| ***REMOVED***215 | **P0** Ingestion read-only filesystem blocker |
| ***REMOVED***214 | PoolTimeout in retryable errors |
| ***REMOVED***213 | PropertyBot timeout regression |

***REMOVED******REMOVED******REMOVED*** Backlog Highlights (P2)

| Issue | Title |
|-------|-------|
| ***REMOVED***133 | Kommo CRM integration epic |
| ***REMOVED***137 | LiteLLM tool-calling ReAct loop |
| ***REMOVED***140 | 3-tier memory (Redis + Kommo + Qdrant) |
| ***REMOVED***142 | Multi-agent handoff protocol |
| ***REMOVED***147 | Latency breakdown (queue, TTFT, decode) |
| ***REMOVED***106 | BGE-M3 ONNX backend |
| ***REMOVED***127 | LLM-as-a-Judge calibration |

---

***REMOVED******REMOVED*** Key Design Decisions

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

***REMOVED******REMOVED*** Python Dependencies (87 packages)

<details>
<summary>Full list grouped by category</summary>

***REMOVED******REMOVED******REMOVED*** Core (8)
python-dotenv, uvloop, aiohttp, requests, httpx, tenacity, asyncpg, pydantic

***REMOVED******REMOVED******REMOVED*** ML & Embeddings (7)
torch (CPU), torchvision, sentence-transformers, FlagEmbedding, transformers, scipy, numpy

***REMOVED******REMOVED******REMOVED*** LLM (4)
anthropic, openai, groq, voyageai

***REMOVED******REMOVED******REMOVED*** Document Processing (4)
pymupdf, docling, docling-core, cocoindex

***REMOVED******REMOVED******REMOVED*** Database & Cache (4)
qdrant-client, fastembed, redis, redisvl

***REMOVED******REMOVED******REMOVED*** LangGraph (5)
langgraph, langchain-core, langgraph-checkpoint-postgres, langgraph-checkpoint-redis, langmem

***REMOVED******REMOVED******REMOVED*** Observability (4)
langfuse, mlflow, ragas, datasets

***REMOVED******REMOVED******REMOVED*** Bot (2)
aiogram, pandas

***REMOVED******REMOVED******REMOVED*** Voice (8)
livekit-agents, livekit-plugins-elevenlabs, livekit-plugins-openai, livekit, fastapi, uvicorn, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http

***REMOVED******REMOVED******REMOVED*** Dev (17)
ruff, mypy, pylint, bandit, vulture, pytest, pytest-cov, pytest-asyncio, pytest-httpx, pytest-timeout, pytest-xdist, opentelemetry-exporter-otlp-proto-grpc, pre-commit, telethon, mkdocs, mkdocs-material, mkdocstrings

</details>

---

***REMOVED******REMOVED*** Quick Commands

```bash
***REMOVED*** Development
uv sync                              ***REMOVED*** Install deps
make check                           ***REMOVED*** Lint + types
make test-unit                       ***REMOVED*** Unit tests
uv run pytest tests/unit/ -n auto    ***REMOVED*** Parallel tests (~5 min)

***REMOVED*** Docker
make docker-core-up                  ***REMOVED*** 5 services, ~17s
make docker-bot-up                   ***REMOVED*** + bot
make docker-full-up                  ***REMOVED*** All 16+ services

***REMOVED*** Evaluation
make eval-rag                        ***REMOVED*** RAGAS faithfulness >= 0.8
make validate-traces-fast            ***REMOVED*** Trace validation

***REMOVED*** Deployment
make k3s-bot                         ***REMOVED*** Deploy to VPS
make k3s-status                      ***REMOVED*** Check pods

***REMOVED*** Monitoring
make monitoring-up                   ***REMOVED*** Loki + Alertmanager
make monitoring-test-alert           ***REMOVED*** Test Telegram alert
```

---

***REMOVED******REMOVED*** Project Stats

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
