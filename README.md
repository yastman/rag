<div align="center">

# Contextual RAG Pipeline

**AI-powered Telegram bot for real estate — RAG search, apartment finder, voice calls, CRM automation**

[![CI](https://github.com/yastman/rag/actions/workflows/ci.yml/badge.svg)](https://github.com/yastman/rag/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

</div>

---

## What is this?

A **production system** that lets real estate clients ask questions in natural language via Telegram — about properties, legal processes, immigration, and more — and get accurate, sourced answers powered by RAG.

**The problem:** Real estate agencies drown in repetitive client questions across Telegram, phone, and CRM. Agents spend hours answering the same things.

**The solution:** An AI-powered Telegram bot that:
- Answers knowledge-base questions with source citations (RAG)
- Searches apartment listings with natural language — *"2-bedroom in Sofia under €80k"*
- Scores and nurtures leads automatically via CRM integration
- Handles voice calls with a LiveKit-powered voice agent

> This runs in production, handles real users, and deploys automatically via CI/CD to a VPS.

---

## How It Works

```mermaid
graph TB
    subgraph "User Interface"
        U["👤 Telegram User"]
        V["📞 Voice Call"]
    end

    subgraph "Bot Layer"
        B["Telegram Bot<br/>aiogram 3 + dialogs"]
        VA["Voice Agent<br/>LiveKit + ElevenLabs"]
    end

    subgraph "Intelligence"
        QC[Query Classifier]
        QC -->|Knowledge| RAG[RAG Pipeline]
        QC -->|Apartment| APT["Apartment Search<br/>regex filters → hybrid search"]
        QC -->|CRM Action| AG["LangGraph Agent<br/>8 CRM tools"]
    end

    subgraph "Retrieval"
        RAG --> SC{Semantic Cache}
        SC -->|HIT| RES[Cached Response]
        SC -->|MISS| HS["Hybrid Search<br/>Dense + Sparse RRF"]
        HS --> RR[ColBERT Rerank]
        RR --> LLM["LLM Generate<br/>via LiteLLM"]
    end

    subgraph "Infrastructure"
        QD[("Qdrant<br/>vectors")]
        RD[("Redis<br/>cache + state")]
        PG[("PostgreSQL<br/>leads + checkpoints")]
        BGE["BGE-M3<br/>embeddings"]
        LF["Langfuse<br/>tracing"]
        CRM[Kommo CRM]
    end

    U --> B --> QC
    V --> VA --> QC
    HS --> QD
    HS --> BGE
    SC --> RD
    AG --> CRM
    AG --> PG
    LLM --> LF
```

---

## Key Features

### Hybrid Search with ColBERT Reranking
Dense + sparse vectors fused via RRF, with optional ColBERT multi-vector reranking — all server-side in Qdrant. No external reranking API needed.

### Zero-Cost Apartment Search
Natural language queries like *"3 rooms in Burgas under 100k"* are parsed with regex first (zero LLM cost). LLM extraction kicks in only for complex queries. Results come from hybrid vector search over property listings.

### Agentic RAG with CRM Tools
LangGraph state graph with 8 tools: create leads, schedule viewings, search history, escalate to human agent. Full HITL (human-in-the-loop) support via `interrupt()`.

### Multi-Level Semantic Cache
Two-tier caching via RedisVL: embedding cache (skip re-encoding) + query result cache (skip retrieval + generation). Distance thresholds tuned per query type. ~60% hit rate in production.

### Voice Assistant
LiveKit Agents + ElevenLabs TTS + OpenAI STT. Handles inbound SIP calls, routes through the same RAG pipeline, responds with natural speech.

### Full Observability
Every LLM call, retrieval, and cache hit/miss traced in Langfuse. 14 RAG quality scores computed per query. Loki + Alertmanager for infrastructure monitoring.

### i18n Ready
Three languages (ru/uk/en) via Fluent `.ftl` files. Locale auto-detection with fallback chains.

### Unified Ingestion
CocoIndex pipeline: Docling parses PDFs/DOCX → semantic chunking → BGE-M3 dense+sparse embeddings → Qdrant. Incremental updates, resumable.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **LLM** | Any model via LiteLLM | Provider-agnostic, easy switching |
| **Embeddings** | BGE-M3 (self-hosted) | Dense + sparse + ColBER in one model, no API costs |
| **Vector DB** | Qdrant | Native RRF fusion, ColBERT support, server-side reranking |
| **Cache** | Redis + RedisVL | Semantic similarity cache, sub-ms latency |
| **Bot** | aiogram 3 + aiogram-dialog | Async, dialog state machines, inline keyboards |
| **Pipeline** | LangGraph | State graph with tools, checkpointing, HITL |
| **Ingestion** | CocoIndex + Docling | Deterministic, resumable, multi-format parsing |
| **Voice** | LiveKit Agents | WebRTC + SIP, plugin ecosystem |
| **Observability** | Langfuse + Loki | LLM tracing + log aggregation + alerting |
| **Database** | PostgreSQL | Lead scoring, graph checkpoints, user data |
| **Deployment** | Docker Compose / k3s | Dev → VPS with CI/CD auto-deploy |

---

## Quick Start

### Prerequisites

- Python 3.11+ (3.12 recommended), [uv](https://docs.astral.sh/uv/), Docker

### 1. Install & Configure

```bash
git clone https://github.com/yastman/rag.git && cd rag
uv sync
cp .env.example .env   # Fill in API keys (see below)
```

### 2. Start Services

```bash
make local-up    # Redis, Qdrant, BGE-M3, Docling, LiteLLM
make run-bot     # Run bot natively (fast iteration, no Docker rebuild)
```

### 3. Or Run Everything in Docker

```bash
make docker-bot-up     # Core + bot (production-like)
make docker-full-up    # All 23 services
```

<details>
<summary><strong>Optional Stacks</strong></summary>

| Stack | Command | Services |
|-------|---------|----------|
| ML/Observability | `make docker-ml-up` | Langfuse, MLflow, ClickHouse, MinIO |
| Monitoring | `make monitoring-up` | Loki, Promtail, Alertmanager |
| Ingestion | `make docker-ingest-up` | Unified ingestion service |
| Voice | `make docker-voice-up` | RAG API, LiveKit, SIP, Voice Agent |

</details>

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram Bot API token |
| `OPENAI_API_KEY` | Yes | OpenAI API key (routed through LiteLLM) |
| `REDIS_PASSWORD` | Yes | Redis authentication |
| `LANGFUSE_*` | Yes | Langfuse observability (public key, secret key, host) |

<details>
<summary><strong>Optional variables</strong></summary>

| Variable | Description |
|----------|-------------|
| `KOMMO_*` | Kommo CRM integration (client ID, secret, tokens) |
| `LIVEKIT_*` | LiveKit voice agent (URL, API key, secret) |
| `CEREBRAS_API_KEY` | Alternative LLM provider |
| `TTFT_DRIFT_WARN_MS` | TTFT monitoring threshold (default: 500ms) |

</details>

---

## Project Structure

```
telegram_bot/              # Telegram bot (aiogram 3 + aiogram-dialog)
├── handlers/              #   Message & callback handlers
├── services/              #   Business logic (search, LLM, cache, apartments, CRM)
├── graph/                 #   LangGraph voice RAG pipeline (11 nodes)
├── agents/                #   Sub-agents (history search, HITL)
├── dialogs/               #   Dialog UI (menus, filters, settings)
├── integrations/          #   External clients (Redis, Postgres, Langfuse)
├── middlewares/           #   Throttling, i18n, error handling
└── locales/{ru,uk,en}/    #   Fluent .ftl translations

src/
├── ingestion/unified/     #   CocoIndex ingestion pipeline
├── retrieval/             #   Search engines & evaluation
├── voice/                 #   LiveKit voice agent
└── api/                   #   FastAPI RAG API

mini_app/                  # Telegram Mini App (React + TypeScript)
k8s/                       # Kubernetes manifests (k3s deployment)
src/evaluation/            # RAG evaluation (RAGAS, A/B testing)
```

## Entry Points

| Service | Command |
|---------|---------|
| Telegram Bot | `uv run python -m telegram_bot.main` |
| RAG API | `uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080` |
| Ingestion CLI | `uv run python -m src.ingestion.unified.cli --help` |
| Voice Agent | `uv run python -m src.voice.agent` |

## Validation

```bash
make check       # Ruff lint + MyPy strict type checking
make test-unit   # Unit tests (parallel via pytest-xdist)
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [DOCKER.md](DOCKER.md) | Docker Compose profiles, service map, env requirements |
| [Architecture](docs/PROJECT_STACK.md) | System architecture and subsystem map |
| [Pipeline Overview](docs/PIPELINE_OVERVIEW.md) | Ingestion, query, and voice runtime flows |
| [Local Development](docs/LOCAL-DEVELOPMENT.md) | Local setup and validation guide |
| [Qdrant Stack](docs/QDRANT_STACK.md) | Vector collections, schema, operations |
| [Ingestion Runbook](docs/INGESTION.md) | Unified ingestion guide and troubleshooting |
| [SDK Migration Audit](docs/SDK_MIGRATION_AUDIT_2026-03-13.md) | Canonical SDK keeper stack and bounded follow-up work |
| [SDK Migration Roadmap](docs/SDK_MIGRATION_ROADMAP_2026-03-13.md) | Post-audit execution order and guardrails |
| [Alerting](docs/ALERTING.md) | Loki/Alertmanager setup |

---

## License

This project is licensed under the [MIT License](LICENSE).
