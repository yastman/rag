# AI Real Estate Automation Platform - Resume Case Study

This document is a resume/portfolio source file. It summarizes the project as a
case study, not as developer setup documentation.

## One-Line Positioning

AI-native real-estate automation platform combining Telegram, RAG search,
apartment matching, CRM automation, voice input, observability, and Dockerized
AI infrastructure.

## Resume Summary - English

Built a production-like AI real-estate automation platform with Telegram bot,
RAG search, natural-language apartment search, Kommo CRM workflows, voice input,
and Docker Compose based local/VPS infrastructure. Implemented self-hosted BGE-M3
embeddings, Qdrant hybrid retrieval with dense/sparse/ColBERT vectors, tiered
Redis caching, semantic conversation memory, CRM lead automation with
human-in-the-loop confirmation, Langfuse tracing, gold-set/evaluation tooling,
and unified document ingestion. The system includes 20+ Docker services,
local/dev observability and monitoring, and 400+ test files.

## Resume Summary - Russian

Разработал AI-native платформу автоматизации для real estate: Telegram-бот,
RAG-поиск, подбор объектов по естественному языку, интеграция с Kommo CRM,
голосовой ввод и Docker-инфраструктура для локального/VPS запуска. Реализовал
self-hosted BGE-M3 embeddings, Qdrant hybrid retrieval с dense/sparse/ColBERT
векторами, многоуровневое Redis-кеширование, семантическую память диалогов,
автоматизацию лидов в CRM с human-in-the-loop подтверждением, Langfuse
трассировку, gold-set/evaluation tooling и unified ingestion документов.

## Best Resume Bullets

- Built an AI automation platform for real-estate workflows with Telegram,
  voice, CRM, RAG, apartment search, and mini-app surfaces.
- Implemented self-hosted retrieval infrastructure using BGE-M3 and Qdrant:
  dense vectors, sparse BM42 vectors, and ColBERT multivector reranking.
- Designed a tiered Redis cache for semantic answers, embeddings, search
  results, and rerank results to reduce latency and LLM cost.
- Connected AI conversations to Kommo CRM: lead/contact/task/note tools, lead
  scoring, manager workflows, and HITL approval before write operations.
- Added Langfuse observability with traces, prompt metadata, quality and
  operational scores, latency/cache/rerank metrics, trace validation, and
  evaluation tooling.
- Built a deterministic ingestion pipeline: Google Drive/local files, Docling
  parsing, chunking, BGE-M3 embeddings, Qdrant upserts/deletes, Postgres state,
  retries, and DLQ.
- Dockerized the system with Compose profiles for bot, ingestion, voice, ML
  observability, monitoring, and full-stack runtime; k3s manifests cover core
  services as an incremental migration path.

## Feature Cards

### 1. LangGraph RAG Pipeline

**Problem:** Real-estate clients ask repeated questions about properties, legal
processes, documents, and company workflows. Static FAQ answers are not enough.

**Implementation:** Built a LangGraph pipeline with classification, prompt
injection guard, cache check, retrieval, grading, reranking, query rewriting,
generation, cache store, response, and optional summarization.

**Impact:** The system behaves like a stateful AI workflow, not a simple LLM
wrapper. It can route easy, off-topic, knowledge, apartment, and CRM-related
queries through different paths.

### 2. Self-Hosted Qdrant + BGE-M3 Retrieval

**Problem:** RAG quality, privacy, and cost depend heavily on the retrieval
stack. API-only embeddings are expensive and less controllable.

**Implementation:** Added a local BGE-M3 FastAPI service running `BAAI/bge-m3`
with endpoints for `/encode/dense`, `/encode/sparse`, `/encode/colbert`,
`/encode/hybrid`, `/rerank`, `/health`, and `/metrics`. Qdrant stores named
vectors: `dense` 1024-dim cosine vectors, `bm42` sparse vectors with IDF, and
`colbert` multivectors with MaxSim.

**Impact:** One self-hosted model provides semantic search, lexical search, and
late-interaction reranking. This reduces vendor dependency and makes embedding
cost predictable.

### 3. Qdrant Schema And Ops

**Problem:** Vector search can fail silently when schemas drift or collections
miss required vectors.

**Implementation:** Added Qdrant bootstrap, schema check, strict mode,
collection aliases, ColBERT coverage checks, and resumable ColBERT backfill.
Ingestion uses deterministic point IDs and replace semantics by `file_id`.

**Impact:** Retrieval infrastructure is operated like a real subsystem, with
schema validation, guardrails, and blue/green-ready collection aliases.

### 4. Tiered Redis Cache

**Problem:** RAG systems are expensive and slow when every request recomputes
embeddings, retrieval, reranking, and LLM output.

**Implementation:** Built a tiered Redis cache:
semantic answer cache, dense embedding cache, sparse embedding cache, search
results cache, and rerank results cache. Conversation history also uses Redis
lists for short-term state.

**Impact:** The system can skip unnecessary BGE-M3, Qdrant, rerank, and LLM
work. This shows cost-aware AI engineering, not just prompt usage.

### 5. Semantic Dialogue Memory

**Problem:** AI assistants lose context when each message is treated as a
stateless request.

**Implementation:** Added Qdrant-backed conversation history. Each Q&A turn is
embedded and stored with user/session metadata, then searched semantically with
user isolation. There is also a history sub-graph for retrieve, grade, rewrite,
and summarize behavior.

**Impact:** Managers and AI workflows can recover previous client context,
summarize sessions, and support better handoff.

### 6. Kommo CRM Automation

**Problem:** Leads from Telegram conversations can be lost if they are not
converted into CRM records and follow-up tasks.

**Implementation:** Integrated Kommo CRM tools for getting deals, creating and
updating leads, upserting contacts, adding notes, creating tasks, linking
contacts to deals, searching leads, reading manager leads/tasks, and updating
contacts. Write operations require HITL confirmation for lead/contact mutations.

**Impact:** The bot connects AI conversations to real sales workflow: lead
capture, qualification, follow-up, and manager handoff.

### 7. Natural-Language Apartment Search

**Problem:** Users describe what they want in natural language or voice instead
of filling structured filters.

**Implementation:** Built an apartment extraction pipeline that converts queries
into structured filters such as city, complex, rooms, price, area, floor, view,
and furnishing. The pipeline uses cached extraction, LLM extraction, and a
deterministic regex fallback. Search results support catalog navigation,
pagination, cards, favorites, and viewing flow.

**Impact:** Users can search with phrases like "2-bedroom near the sea under
120k", while the system still applies structured filters and avoids unnecessary
LLM work when deterministic parsing is enough.

### 8. Voice Input And Voice Agent

**Problem:** Real-estate clients may prefer voice messages or phone-like flows
instead of text.

**Implementation:** Added Telegram voice input and a LiveKit RTC voice path
with ElevenLabs STT/TTS. The voice agent calls the same RAG API used by other
channels and propagates Langfuse trace IDs for continuity. SIP support is
represented as outbound trunk provisioning rather than a fully documented
inbound call-routing flow.

**Impact:** One AI workflow works across text, Telegram voice, and voice-agent
channels.

### 9. Unified Document Ingestion

**Problem:** RAG quality depends on reliable document ingestion, not only on the
chatbot layer.

**Implementation:** Built a unified ingestion pipeline: Google Drive/local
files, stable file identity, Docling parsing, chunking, BGE-M3 embeddings,
Qdrant upsert/delete, Postgres state, retries, DLQ, and status commands. On
local BGE-M3, ingestion uses `/encode/hybrid` to get dense, sparse, and ColBERT
vectors in one model pass.

**Impact:** Knowledge-base updates are deterministic, resumable, and observable.

### 10. Langfuse Observability And Prompt Management

**Problem:** AI workflows are hard to debug without traces, scores, and prompt
version visibility.

**Implementation:** Integrated Langfuse tracing and scores for RAG/API/voice/
ingestion paths. The project tracks latency, cache hits, rerank usage, LLM
usage, TTFT, token metrics, grounding, sources, security alerts, history search,
and CRM tool results. Prompt management uses Langfuse `get_prompt(...)`,
prompt labels, cached prompt retrieval, fallback prompts, `prompt_source`, and
`prompt_version` metadata on spans.

**Impact:** The system can be improved from traces and metrics rather than
manual guessing. Prompt behavior is version-aware and fallback-safe, with
graceful no-op behavior when Langfuse is not configured or unreachable.

### 11. Gold Sets, Evaluation, And Experiments

**Problem:** RAG changes need regression checks against expected answers and
routing behavior.

**Implementation:** Added evaluation assets and commands:
`tests/eval/ground_truth.json`, `tests/eval/agent_routing_golden.yaml`,
baseline metric collection from Langfuse, RAGAS evaluation commands,
gold-set sync to Langfuse datasets, experiment runners, trace export, score
config setup, judge calibration, and trace validation. The checked-in
ground-truth fixture currently contains 55 samples; generation scripts can
produce larger corpus-derived datasets.

**Impact:** Retrieval, generation, routing, and prompt changes can be compared
against gold data and Langfuse experiment/baseline metrics.

### 12. Dockerized Production-Like Runtime

**Problem:** AI projects often work only as local scripts and are hard to run as
a system.

**Implementation:** Created Docker Compose profiles for core services, bot,
ingestion, voice, ML observability, monitoring, and full runtime. The stack
includes Postgres, Redis, Qdrant, BGE-M3, USER2-base, Docling, LiteLLM, bot,
RAG API, LiveKit, mini app, Langfuse, ClickHouse, MinIO, Loki, Promtail, and
Alertmanager. The primary VPS path is GitHub Actions plus Docker Compose; k3s
manifests exist for core services but do not yet cover the full Compose stack.

**Impact:** The project demonstrates operational thinking: service boundaries,
healthchecks, profiles, resource limits, pinned images, local/VPS workflows, and
monitoring. The Loki/Alertmanager stack is best described as local/dev
monitoring unless production deployment evidence is added.

## Technical Highlights

- **LLM orchestration:** LangGraph, LiteLLM, Langfuse OpenAI integration.
- **Retrieval:** Qdrant Query API, RRF fusion, dense/sparse vectors, ColBERT
  multivectors, MaxSim rerank.
- **Embeddings:** self-hosted `BAAI/bge-m3`, local `deepvk/USER2-base` service
  for Russian semantic vectorizer/cache scenarios, optional Voyage paths.
- **Caching:** RedisVL semantic cache, embeddings cache, sparse cache, search
  cache, rerank cache.
- **CRM:** Kommo tools, lead/contact/task/note workflows, HITL approvals,
  manager flows, lead scoring sync.
- **Voice:** Telegram voice input, LiveKit voice agent, shared RAG API.
- **Ingestion:** CocoIndex, Docling, BGE-M3, Qdrant writer, Postgres state/DLQ.
- **Observability:** Langfuse traces, scores, prompt metadata,
  Loki/Alertmanager for local/dev monitoring, trace validation.
- **Evaluation:** gold sets, RAGAS, Langfuse datasets/experiments, baseline
  metrics, judge calibration scripts.
- **Ops:** Docker Compose profiles, healthchecks, pinned images, non-root
  runtime users, VPS Docker Compose deployment path, partial k3s manifests.

## Interview Talking Points

1. **Why BGE-M3?**
   It gives dense, sparse, and ColBERT vectors from one self-hosted model. This
   reduces cost and supports hybrid retrieval without multiple embedding vendors.

2. **Why Qdrant?**
   Qdrant supports named vectors, sparse vectors, multivectors, Query API
   prefetch/fusion flows, and server-side ColBERT-style reranking.

3. **How is cost controlled?**
   The project avoids LLM calls when possible: classification, deterministic
   apartment parsing fallback, semantic cache, embeddings cache, search cache,
   rerank cache, and local embeddings.

4. **How are CRM writes made safe?**
   CRM write tools use human-in-the-loop confirmation before creating/updating
   leads, contacts, or other important records.

5. **How do you debug quality issues?**
   Langfuse traces and scores show retrieval path, cache behavior, rerank usage,
   LLM usage, latency, grounding, prompt source/version, and CRM/history events.

6. **What makes this more than a chatbot?**
   It has ingestion, retrieval infrastructure, CRM automation, voice channel,
   memory, evaluation, observability, and Dockerized runtime services.

## Honest Limitations / Next Improvements

- Fix and revalidate local Langfuse ML profile startup for the pinned ClickHouse
  image.
- Keep k3s wording conservative until manifests cover Langfuse, monitoring,
  mini app, voice, and ingestion runtime parity with Compose.
- Treat Loki/Alertmanager as local/dev monitoring unless production VPS
  evidence is added.
- Add CI or release-gate wiring for `validate_traces.py` and RAGAS evaluation
  instead of keeping them as mostly manual quality tools.
- Add a prompt-version A/B harness using Langfuse labels and dataset
  experiments.
- Add screenshots or short demo videos for Telegram, CRM handoff, Langfuse
  traces, and apartment search.
- Publish a small sanitized demo dataset so recruiters can run a safe subset.
- Add a short architecture diagram optimized for non-engineers.
- Add quantified metrics if available: cache hit rate, latency before/after
  cache, number of indexed documents, successful CRM flows, and RAG eval scores.
