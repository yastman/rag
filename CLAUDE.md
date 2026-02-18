# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference

```bash
uv sync                    # Install all dependencies
make check                 # Lint + types
make test                  # All tests
make test-unit             # Unit tests only (fast)
uv run pytest tests/unit/ -n auto  # Parallel (4x faster, ~5 min)
uv run pytest tests/integration/ -v  # Integration tests (~5s, no Docker)
make docker-up             # Start core services (5 containers, ~17s)
make docker-bot-up         # Core + bot/litellm
make docker-voice-up       # Core + LiveKit/SIP/voice-agent (preflight)
make docker-full-up        # All services (17 containers)
make eval-rag              # RAG evaluation (RAGAS faithfulness >= 0.8)
make eval-goldset-sync     # Sync gold set to Langfuse dataset
make eval-experiment       # Run RAG experiment on gold set
make validate-traces-fast  # Trace validation (cold+cache, Langfuse report)
make monitoring-up         # Start alerting stack
make ingest-unified        # Unified ingestion (CocoIndex v3.2.1); also: -watch, -status
make repo-cleanup          # Repo hygiene: branches, worktrees, stashes (dry-run)
make export-dataset        # Export low-scoring Langfuse traces to evaluation dataset
# VPS CLI: python -m src.ingestion.unified.cli preflight|bootstrap|run|status|reprocess
```

**Location:** `/home/user/projects/rag-fresh` (WSL2) | `/opt/rag-fresh` (VPS)

## Project Overview

**Contextual RAG Pipeline** — Production RAG with hybrid search (RRF + ColBERT rerank), BGE-M3 embeddings (local CPU), multi-level caching, Telegram bot.

**Stack:** Python 3.12 | gpt-oss-120b (Cerebras) via LiteLLM | BGE-M3 (local) | Qdrant | Redis | CocoIndex

**Use cases:** Bulgarian property (192 docs), Ukrainian Criminal Code (1,294 docs)

## Architecture

```
Ingestion:  Docling Parser → Chunker → BGE-M3 Dense + Sparse → Qdrant
Bot:        Query → Supervisor LLM → tool choice (rag_search | history_search | direct_response)
            → rag_search wraps LangGraph 11-node pipeline (with guard node) → respond
            (#310: supervisor-only, monolith path removed)
Voice STT:  Voice (.ogg) → transcribe (Whisper via LiteLLM) → text → same pipeline
Voice Bot:  /call → LiveKit Agent (ElevenLabs STT/TTS) → @function_tool → RAG API (FastAPI)
```

| Module | Purpose |
|--------|---------|
| `telegram_bot/bot.py` | PropertyBot (~300 LOC, supervisor orchestrator + voice handler) |
| `telegram_bot/scoring.py` | `write_langfuse_scores()` + `compute_checkpointer_overhead_proxy_ms()` (#310) |
| `telegram_bot/graph/` | LangGraph 11-node RAG pipeline (guard, transcribe, classify, cache, retrieve, grade, rerank, generate, rewrite, cache_store, respond) |
| `telegram_bot/graph/nodes/guard.py` | Content filtering: toxicity, prompt injection, topic guardrails (regex, configurable via GUARD_MODE) |
| `telegram_bot/agents/` | Multi-agent supervisor architecture (#240): tools, rag_agent, history_agent, supervisor |
| `telegram_bot/integrations/` | Cache (Redis pipelines), embeddings, langfuse, prompt mgmt |
| `telegram_bot/services/bge_m3_client.py` | Unified BGE-M3 SDK (BGEM3Client async + BGEM3SyncClient) — replaces separate wrappers |
| `telegram_bot/services/` | LLM, Qdrant (gRPC + batch), preprocessing, reranker |
| `telegram_bot/observability.py` | Langfuse init, @observe decorator, PII masking |
| `src/api/` | RAG API (FastAPI wrapper around LangGraph, POST /query) |
| `src/voice/` | Voice Bot (LiveKit Agent + ElevenLabs + SIP trunk + transcripts) |
| `src/retrieval/search_engines.py` | 4 search variants (evaluation) |
| `src/ingestion/unified/` | Unified pipeline v3.2.1 (CocoIndex) |
| `telegram_bot/evaluation/` | LLM-as-a-Judge (RAG Triad: faithfulness, relevance, context) |
| `scripts/validate_*.py` | Trace validation runner + query goldset |
| `scripts/export_traces_to_dataset.py` | Export low-scoring Langfuse traces to versioned evaluation datasets |

**Services:** Qdrant:6333 (gRPC:6334), Redis:6379, LiteLLM:4000, Langfuse:3001, LiveKit:7880, RAG API:8080

**Observability:** Langfuse v3 — 35 observations/trace, 21 scores (14 RAG + 4 /history + 3 supervisor) + 3 judge scores, curated spans on 6 heavy nodes, error spans on 4 nodes → see `.claude/rules/observability.md`

**Docker Profiles:** `core` (5 svc, ~17s) | `bot` | `ml` | `obs` | `ai` | `eval` | `ingest` | `voice` (LiveKit + SIP + RAG API) | `full` → see `.claude/rules/docker.md`

## Code Style

- **Linter/Formatter:** Ruff | **Types:** MyPy (strict in CI) | **Line length:** 100 | **Docstrings:** Google style
- **Pre-commit:** ruff-check (--fix) → ruff-format → trailing-whitespace → check-yaml/toml/json
- **CI:** lint (ruff + mypy) → test-fast (PR gate, 4 shards) → test-nightly (chaos/load/E2E) → baseline-compare (PR only)
- **Commits:** `feat(scope): message` | `fix(scope): message` | `docs(scope): message`

## Dependency Management

**Mend Renovate** tracks all deps automatically: Python, Docker, GH Actions, pre-commit hooks.

- **Dashboard:** [developer.mend.io/github/yastman/rag](https://developer.mend.io/github/yastman/rag) | Issue #11
- **Config:** `renovate.json` | Schedule: Monday before 9:00 Kyiv
- **Skill:** `/deps` — review and merge updates
- **Lock maintenance:** `uv.lock` refreshed weekly via Renovate
- **PR workflow:** `.claude/rules/git-workflow.md` — PR size limits, merge discipline, Renovate batching

## Task Management

**Active:** `TODO.md` | **Backlog:** `gh issue list --label "next"` | **Shared tasks:** `CLAUDE_CODE_TASK_LIST_ID=X claude` → `.claude/rules/shared-tasks.md`

## Environment

1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Copy `.env.example` → `.env`
3. Required: `TELEGRAM_BOT_TOKEN`, `CEREBRAS_API_KEY`, `OPENAI_API_KEY` (Whisper STT), `LANGFUSE_*`, `REDIS_PASSWORD` | Voice: `ELEVENLABS_API_KEY`, `LIVEKIT_*`, `LIFECELL_SIP_*`
4. `uv sync && make docker-up`

## Key Docs

| Document | Content |
|----------|---------|
| `docs/PIPELINE_OVERVIEW.md` | Architecture |
| `docs/QDRANT_STACK.md` | Vector DB (gRPC, batch, group_by) |
| `docs/INGESTION.md` | Document ingestion pipeline |
| `CACHING.md` | 6-tier cache (Redis pipelines) |

## Qdrant Collections

| Collection | Content | Embeddings | Environment |
|------------|---------|------------|-------------|
| `gdrive_documents_bge` | Google Drive docs | BGE-M3 (dense + sparse) | VPS (production) |
| `contextual_bulgaria_voyage` | Bulgarian property (192 docs) | Voyage | Dev |
| `legal_documents` | Ukrainian Criminal Code (1,294 docs) | BGE-M3 | Dev |
| `gdrive_documents_scalar` | Google Drive docs | Voyage | Dev |

**Settings:** `quantization_mode=off|scalar|binary`, `small_to_big_mode=off|on|auto`, `use_hyde=true|false`, `STREAMING_ENABLED=true|false`, `SHOW_TRANSCRIPTION=true|false`, `VOICE_LANGUAGE=ru`, `STT_MODEL=whisper`, `RELEVANCE_THRESHOLD_RRF=0.005`, `SKIP_RERANK_THRESHOLD=0.012`, `SCORE_IMPROVEMENT_DELTA=0.001`, `QDRANT_TIMEOUT=30`
**Settings:** `quantization_mode=off|scalar|binary`, `small_to_big_mode=off|on|auto`, `use_hyde=true|false`, `STREAMING_ENABLED=true|false`, `SHOW_TRANSCRIPTION=true|false`, `VOICE_LANGUAGE=ru`, `STT_MODEL=whisper`, `RELEVANCE_THRESHOLD_RRF=0.005`, `SKIP_RERANK_THRESHOLD=0.012`, `SCORE_IMPROVEMENT_DELTA=0.001`, `QDRANT_TIMEOUT=30`, `GUARD_MODE=hard|soft|log`, `CONTENT_FILTER_ENABLED=true|false`

## Deployment

```bash
# Dev (Docker Compose)
make docker-up                      # Core services (5 svc, ~17s)
make docker-bot-up                  # + bot

# Build images (parallel via Docker Bake)
docker buildx bake --load           # All 5 custom images
docker buildx bake bot              # Single target

# VPS k3s (local embeddings, no Voyage API)
make k3s-secrets                    # Create k8s secrets
make k3s-push-bot                   # Transfer image to VPS
make k3s-bot                        # Deploy bot stack
make k3s-status                     # Check pods
```

**VPS:** `admin@95.111.252.29:1654` (`ssh vps`) | Path: `/opt/rag-fresh`

**VPS Env:** `RETRIEVAL_DENSE_PROVIDER=bge_m3_api` `RETRIEVAL_SPARSE_PROVIDER=bge_m3_api` `RERANK_PROVIDER=colbert` `BGE_M3_URL=http://bge-m3:8000`

**k3s details:** → see `.claude/rules/k3s.md`

## Monitoring & Alerting

`make monitoring-up` | `make monitoring-test-alert` → See `.claude/rules/docker.md` and `docs/ALERTING.md`

## Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` (requires `REDIS_PASSWORD`, ExponentialBackoff retry) |
| Qdrant timeout | `QDRANT_TIMEOUT=30` (explicit timeout + FormulaQuery for score boosting) |
| Voyage 429 | Use CacheLayerManager |
| Docling 0 chunks | Don't set `tokenizer="word"`, use `None` |
| Alerts not sending | Check `TELEGRAM_ALERTING_*` env vars |

## Repository Hygiene

`make repo-cleanup` (dry-run) | `make repo-cleanup-force` (interactive) — branches, worktrees, stashes. Details: `.claude/rules/git-workflow.md`

## Skills Workflow

```
/writing-plans → /executing-plans → /finishing-a-development-branch
/deps                              — dependency audit (Mend Renovate)
/agent-teams                       — multi-agent coordination
```

**Details:** `.claude/rules/skills.md`

## Modular Docs

See `.claude/rules/` for domain-specific documentation:

| File | Scope | Loads when |
|------|-------|-----------|
| `features/search-retrieval.md` | RRF, gRPC, batch, group_by, quantization | `src/retrieval/**` |
| `features/query-processing.md` | HyDE, preprocessing, routing | `**/query*.py` |
| `features/evaluation.md` | RAGAS, LLM-as-a-Judge, metrics, A/B tests | `src/evaluation/**, telegram_bot/evaluation/**` |
| `features/caching.md` | 6-tier cache, Redis pipelines, TTL | `**/cache*.py` |
| `features/embeddings.md` | BGE-M3 (/encode/hybrid, dense, sparse), Voyage | `**/embed*.py` |
| `features/llm-integration.md` | LiteLLM, guardrails, fallbacks | `**/llm*.py` |
| `features/ingestion.md` | CocoIndex, Docling, parsing | `src/ingestion/**` |
| `features/telegram-bot.md` | LangGraph pipeline, bot, supervisor, middlewares | `telegram_bot/*.py` |
| `features/voice-bot.md` | LiveKit Agent, SIP, RAG API, /call | `src/voice/**, src/api/**` |
| `features/user-personalization.md` | CESC, user context, preferences | `**/user_context*.py` |
| `services.md` | Service/integration patterns, prompt mgmt | `telegram_bot/services/**, telegram_bot/integrations/**` |
| `observability.md` | Langfuse v3, @observe, scores, baseline | `telegram_bot/observability.py, tests/baseline/**` |
| `build.md` | uv, Makefile, pre-commit hooks | `Makefile, pyproject.toml` |
| `docker.md` | Containers, monitoring | `docker/**` |
| `k3s.md` | k3s manifests, deployment, VPS | `k8s/**` |
| `testing.md` | Unit tests, chaos tests, E2E | `tests/**` |
| `skills.md` | Superpowers workflow | `docs/plans/**` |
| `git-workflow.md` | PR discipline, merge rules, Renovate strategy | `.github/**, renovate.json` |
| `shared-tasks.md` | Shared task list between terminals | — |
