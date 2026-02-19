***REMOVED*** Contextual RAG Pipeline

***REMOVED******REMOVED*** What This Is

Production RAG system — Telegram-бот с гибридным поиском (RRF + ColBERT rerank), BGE-M3 embeddings (local CPU), CRM-интеграцией (Kommo: lead scoring, nurturing, funnel analytics), voice (LiveKit + ElevenLabs), и полной observability (Langfuse v3). Два use-case: болгарская недвижимость (192 docs) и Уголовный кодекс Украины (1,294 docs).

***REMOVED******REMOVED*** Core Value

Клиент задаёт вопрос → получает точный, контекстуальный ответ из базы знаний с автоматической CRM-воронкой (scoring → сделка → nurturing).

***REMOVED******REMOVED*** Requirements

***REMOVED******REMOVED******REMOVED*** Validated

- ✓ RAG pipeline: 11-node LangGraph (guard → classify → cache → retrieve → grade → rerank → generate → rewrite → cache_store → respond) — existing
- ✓ Agent SDK: `create_agent` factory с tool routing (rag_search, history_search, 8 CRM tools) — ***REMOVED***413
- ✓ Hybrid search: BGE-M3 dense+sparse → RRF merge → optional ColBERT rerank — existing
- ✓ 6-tier Redis caching: embedding → search → response (TTL, pipelines) — existing
- ✓ Voice STT: .ogg → Whisper via LiteLLM → text → same pipeline — existing
- ✓ Voice Bot: LiveKit Agent + ElevenLabs STT/TTS + SIP trunk → RAG API — existing
- ✓ CRM integration: KommoClient (OAuth2 auto-refresh), lead scoring, nurturing scheduler, funnel analytics — ***REMOVED***384, ***REMOVED***390
- ✓ Langfuse observability: 35 observations/trace, 29 scores, PII masking, @observe — existing
- ✓ Content filtering: guard_node (regex toxicity + injection detection, GUARD_MODE) — existing (voice path only)
- ✓ Ingestion: CocoIndex v3.2.1 unified pipeline (Docling → chunk → BGE-M3 → Qdrant) — existing
- ✓ Docker + k3s deployment: profiles (core/bot/ml/obs/ai/eval/ingest/voice/full), VPS at REDACTED_VPS_IP — existing
- ✓ CI/CD: ruff + mypy → pytest 4-shard → baseline-compare → nightly chaos/load — existing

***REMOVED******REMOVED******REMOVED*** Active

- [ ] Pipeline refactor: 11-node graph → 6-step async tool (simplified RAG pipeline) — ***REMOVED***442
- [ ] CRM tools test coverage: 5/8 untested + error path tests — ***REMOVED***441
- [ ] CRM-specific Langfuse scores: 4 new scores for agent tool usage — ***REMOVED***440
- [ ] History guard: injection/toxicity filtering for history_search sub-graph — ***REMOVED***432
- [ ] Security: text path guard bypass fix (3 critical gaps) — ***REMOVED***439
- [ ] E2E runtime gate: full CI mocks + live Telethon smoke — ***REMOVED***406
- [ ] Epic E2E: все фичи в продакшн-боте (menu + воронка + CRM + история + менеджер) — ***REMOVED***403
- [ ] Menu skeleton: client/manager/CRM dialogs + tool mapping — ***REMOVED***447
- [ ] Extended CRM tools + HITL confirmation flow — ***REMOVED***443
- [ ] Menu expansion (client 9 + manager 9) + i18n system prompt — ***REMOVED***444
- [ ] New tools (mortgage, daily_summary, handoff) + background workers — ***REMOVED***445
- [ ] E2E tests + cleanup + close epic — ***REMOVED***446

***REMOVED******REMOVED******REMOVED*** Out of Scope

- Multimodal RAG (images/tables) — high complexity, defer to v3+ (***REMOVED***379)
- GraphRAG (Neo4j knowledge graph) — infrastructure overhead, not justified for current use cases (***REMOVED***377)
- Automated red teaming (DeepTeam) — research phase, not production ready (***REMOVED***378)
- Presidio PII protection — current regex PII masking sufficient for now (***REMOVED***376)
- Mobile app — Telegram is the interface
- Real-time chat — bot is async Q&A, not live chat

***REMOVED******REMOVED*** Context

**Текущий спринт (P1-next):** 4 параллельных worker issues (***REMOVED***442, ***REMOVED***441, ***REMOVED***440, ***REMOVED***432) в tmux swarm.

**Epic ***REMOVED***403:** Canonical dependency chain `***REMOVED***312 → ***REMOVED***389 → ***REMOVED***384 → ***REMOVED***390 → ***REMOVED***402`. Готово: ***REMOVED***395, ***REMOVED***383, ***REMOVED***388. В работе: pipeline refactor + CRM hardening. Blocked: phases 2-5 (menu, HITL, new tools, E2E).

**Known critical bugs:**
- ***REMOVED***439: Text path bypasses guard node (security — CRM tools exploitable)
- ***REMOVED***428: Streaming coordination broken (duplicate responses)
- ***REMOVED***430: Semantic cache ineffective (agent reformulates queries)
- ***REMOVED***427: Online LLM-as-a-Judge removed in ***REMOVED***413 migration

**Tech debt:**
- APScheduler v3 → v4 migration pending
- MLflow integration stubs (hardcoded metrics)
- Database pool timeout not enforced
- Response style detection disabled

**Deployment:**
- Dev: Docker Compose (WSL2, `/repo`)
- Prod: k3s cluster (VPS `admin@REDACTED_VPS_ENDPOINT`, `/opt/rag-fresh`)
- BGE-M3 local API (CPU), Cerebras gpt-oss-120b via LiteLLM

***REMOVED******REMOVED*** Constraints

- **Stack**: Python 3.12, uv, LangGraph/langchain-core, aiogram 3.x — locked
- **LLM**: Cerebras gpt-oss-120b via LiteLLM (cost-efficient, fast) — primary provider
- **Embeddings**: BGE-M3 local CPU (no Voyage API on VPS) — dense+sparse hybrid
- **Vector DB**: Qdrant (gRPC, batch, group_by) — committed
- **CRM**: Kommo API v4 (OAuth2, Redis token store) — committed
- **Infra**: Single VPS (4-8 cores, 8-16GB RAM, 100GB SSD) — scaling limit
- **CI**: pytest-xdist 4 shards, pre-commit (ruff+mypy), Renovate deps — enforced

***REMOVED******REMOVED*** Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Agent SDK (`create_agent`) over supervisor graph | Simpler tool routing, better DI via BotContext, less LangGraph complexity | ✓ Good (***REMOVED***413) |
| BGE-M3 local over Voyage API | No API costs on VPS, dense+sparse in one model | ✓ Good |
| RRF + optional ColBERT rerank | Two-stage relevance: fast RRF → precise ColBERT on low-confidence | ✓ Good |
| 6-tier Redis caching | Reduce LLM/embedding calls by 80%+ on repeated queries | ✓ Good |
| Langfuse v3 over custom metrics | Managed evaluators, trace UI, PII masking built-in | ✓ Good |
| Pipeline refactor to 6-step async | Reduce LangGraph complexity, faster iteration on tool logic | — Pending (***REMOVED***442) |
| Guard node for all paths (text+voice+history) | Fix ***REMOVED***439 security gap | — Pending (***REMOVED***439, ***REMOVED***432) |

---
*Last updated: 2026-02-19 after GSD initialization*
