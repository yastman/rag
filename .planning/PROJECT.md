# Contextual RAG Pipeline

## What This Is

Production RAG system — Telegram-бот с гибридным поиском (RRF + ColBERT rerank), BGE-M3 embeddings (local CPU), CRM-интеграцией (Kommo: lead scoring, nurturing, funnel analytics), voice (LiveKit + ElevenLabs), и полной observability (Langfuse v3). Два use-case: болгарская недвижимость (192 docs) и Уголовный кодекс Украины (1,294 docs).

## Core Value

Клиент задаёт вопрос → получает точный, контекстуальный ответ из базы знаний с автоматической CRM-воронкой (scoring → сделка → nurturing).

## Requirements

### Validated

- ✓ RAG pipeline: 11-node LangGraph (guard → classify → cache → retrieve → grade → rerank → generate → rewrite → cache_store → respond) — existing
- ✓ Agent SDK: `create_agent` factory с tool routing (rag_search, history_search, 8 CRM tools) — #413
- ✓ Hybrid search: BGE-M3 dense+sparse → RRF merge → optional ColBERT rerank — existing
- ✓ 6-tier Redis caching: embedding → search → response (TTL, pipelines) — existing
- ✓ Voice STT: .ogg → Whisper via LiteLLM → text → same pipeline — existing
- ✓ Voice Bot: LiveKit Agent + ElevenLabs STT/TTS + SIP trunk → RAG API — existing
- ✓ CRM integration: KommoClient (OAuth2 auto-refresh), lead scoring, nurturing scheduler, funnel analytics — #384, #390
- ✓ Langfuse observability: 35 observations/trace, 29 scores, PII masking, @observe — existing
- ✓ Content filtering: guard_node (regex toxicity + injection detection, GUARD_MODE) — existing (voice path only)
- ✓ Ingestion: CocoIndex v3.2.1 unified pipeline (Docling → chunk → BGE-M3 → Qdrant) — existing
- ✓ Docker + k3s deployment: profiles (core/bot/ml/obs/ai/eval/ingest/voice/full), VPS at 95.111.252.29 — existing
- ✓ CI/CD: ruff + mypy → pytest 4-shard → baseline-compare → nightly chaos/load — existing

### Active

- [ ] Pipeline refactor: 11-node graph → 6-step async tool (simplified RAG pipeline) — #442
- [ ] CRM tools test coverage: 5/8 untested + error path tests — #441
- [ ] CRM-specific Langfuse scores: 4 new scores for agent tool usage — #440
- [ ] History guard: injection/toxicity filtering for history_search sub-graph — #432
- [ ] Security: text path guard bypass fix (3 critical gaps) — #439
- [ ] E2E runtime gate: full CI mocks + live Telethon smoke — #406
- [ ] Epic E2E: все фичи в продакшн-боте (menu + воронка + CRM + история + менеджер) — #403
- [ ] Menu skeleton: client/manager/CRM dialogs + tool mapping — #447
- [ ] Extended CRM tools + HITL confirmation flow — #443
- [ ] Menu expansion (client 9 + manager 9) + i18n system prompt — #444
- [ ] New tools (mortgage, daily_summary, handoff) + background workers — #445
- [ ] E2E tests + cleanup + close epic — #446

### Out of Scope

- Multimodal RAG (images/tables) — high complexity, defer to v3+ (#379)
- GraphRAG (Neo4j knowledge graph) — infrastructure overhead, not justified for current use cases (#377)
- Automated red teaming (DeepTeam) — research phase, not production ready (#378)
- Presidio PII protection — current regex PII masking sufficient for now (#376)
- Mobile app — Telegram is the interface
- Real-time chat — bot is async Q&A, not live chat

## Context

**Текущий спринт (P1-next):** 4 параллельных worker issues (#442, #441, #440, #432) в tmux swarm.

**Epic #403:** Canonical dependency chain `#312 → #389 → #384 → #390 → #402`. Готово: #395, #383, #388. В работе: pipeline refactor + CRM hardening. Blocked: phases 2-5 (menu, HITL, new tools, E2E).

**Known critical bugs:**
- #439: Text path bypasses guard node (security — CRM tools exploitable)
- #428: Streaming coordination broken (duplicate responses)
- #430: Semantic cache ineffective (agent reformulates queries)
- #427: Online LLM-as-a-Judge removed in #413 migration

**Tech debt:**
- APScheduler v3 → v4 migration pending
- MLflow integration stubs (hardcoded metrics)
- Database pool timeout not enforced
- Response style detection disabled

**Deployment:**
- Dev: Docker Compose (WSL2, `/home/user/projects/rag-fresh`)
- Prod: k3s cluster (VPS `admin@95.111.252.29:1654`, `/opt/rag-fresh`)
- BGE-M3 local API (CPU), Cerebras gpt-oss-120b via LiteLLM

## Constraints

- **Stack**: Python 3.12, uv, LangGraph/langchain-core, aiogram 3.x — locked
- **LLM**: Cerebras gpt-oss-120b via LiteLLM (cost-efficient, fast) — primary provider
- **Embeddings**: BGE-M3 local CPU (no Voyage API on VPS) — dense+sparse hybrid
- **Vector DB**: Qdrant (gRPC, batch, group_by) — committed
- **CRM**: Kommo API v4 (OAuth2, Redis token store) — committed
- **Infra**: Single VPS (4-8 cores, 8-16GB RAM, 100GB SSD) — scaling limit
- **CI**: pytest-xdist 4 shards, pre-commit (ruff+mypy), Renovate deps — enforced

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Agent SDK (`create_agent`) over supervisor graph | Simpler tool routing, better DI via BotContext, less LangGraph complexity | ✓ Good (#413) |
| BGE-M3 local over Voyage API | No API costs on VPS, dense+sparse in one model | ✓ Good |
| RRF + optional ColBERT rerank | Two-stage relevance: fast RRF → precise ColBERT on low-confidence | ✓ Good |
| 6-tier Redis caching | Reduce LLM/embedding calls by 80%+ on repeated queries | ✓ Good |
| Langfuse v3 over custom metrics | Managed evaluators, trace UI, PII masking built-in | ✓ Good |
| Pipeline refactor to 6-step async | Reduce LangGraph complexity, faster iteration on tool logic | — Pending (#442) |
| Guard node for all paths (text+voice+history) | Fix #439 security gap | — Pending (#439, #432) |

---
*Last updated: 2026-02-19 after GSD initialization*
