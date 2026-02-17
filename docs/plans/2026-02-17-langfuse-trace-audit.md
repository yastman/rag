# Langfuse Trace Coverage Audit

**Date:** 2026-02-17
**Issue:** #241
**Branch:** epic/supervisor-migration-263

## 1. Entry Points

| Entry Point | @observe | propagate_attrs | update_trace | scores | error spans | Gap? |
|-------------|----------|-----------------|--------------|--------|-------------|------|
| `handle_query` (bot.py:628) | `telegram-rag-query` | session+user+tags | input/output/metadata | 14 + 3 judge | via nodes | **NONE** |
| `handle_voice` (bot.py:748) | `telegram-rag-voice` | session+user+tags+voice | input/output/metadata | 14 + voice scores | via nodes | **NONE** |
| `cmd_history` (bot.py:550) | `telegram-history-search` | session+user+tags | input/output/metadata | 4 scores | no error span | **Minor** |
| `handle_feedback` (bot.py:921) | — | — | — | `user_feedback` (existing trace) | — | **Low** (by design) |
| `cmd_start` (bot.py:388) | — | — | — | — | — | **Low** — utility |
| `cmd_help` (bot.py:400) | — | — | — | — | — | **Low** — utility |
| `cmd_clear` (bot.py:422) | — | — | — | — | — | **Low** — churn signal |
| `cmd_stats` (bot.py:444) | — | — | — | — | — | **Low** — utility |
| `cmd_metrics` (bot.py:460) | — | — | — | — | — | **Low** — utility |
| `cmd_call` (bot.py:466) | — | — | — | — | — | **MEDIUM** — untraced |
| FastAPI `/query` (api/main.py:103) | — (no decorator) | session+user+tags | input/output/metadata | 14 (via `_write_langfuse_scores`) | via nodes | **Minor** |
| Voice Agent `entrypoint` (voice/agent.py:181) | — | — (LiveKit OTEL) | — | — | — | **MEDIUM** — OTEL only |

## 2. Graph Nodes (10/10 covered)

| Node | @observe | capture_input/output | curated spans | error spans |
|------|----------|---------------------|---------------|-------------|
| classify | `node-classify` | auto | — | — |
| cache_check | `node-cache-check` | `False/False` | input+output | embedding error |
| cache_store | `node-cache-store` | `False/False` | input+output | — |
| retrieve | `node-retrieve` | `False/False` | input+output | — |
| grade | `node-grade` | auto | — | — |
| rerank | `node-rerank` | auto | — | ColBERT fail |
| generate | `node-generate` | `False/False` | input+output | LLM fail + streaming warn |
| rewrite | `node-rewrite` | auto | — | LLM rewrite fail |
| respond | `node-respond` | `False/False` | input+output | Telegram send fail |
| transcribe | `transcribe` | `False/False` | input+output | — (raises; caught upstream) |

## 3. Score Parity (Telegram vs FastAPI vs Voice)

| Score | Telegram | FastAPI /query | Voice Agent |
|-------|----------|----------------|-------------|
| query_type | ✅ | ✅ | ❌ |
| latency_total_ms | ✅ | ✅ | ❌ |
| semantic_cache_hit | ✅ | ✅ | ❌ |
| embeddings_cache_hit | ✅ | ✅ | ❌ |
| search_cache_hit | ✅ | ✅ | ❌ |
| rerank_applied | ✅ | ✅ | ❌ |
| rerank_cache_hit | ✅ | ✅ | ❌ |
| results_count | ✅ | ✅ | ❌ |
| no_results | ✅ | ✅ | ❌ |
| llm_used | ✅ | ✅ | ❌ |
| confidence_score | ✅ | ✅ | ❌ |
| hyde_used | ✅ | ✅ | ❌ |
| llm_ttft_ms | ✅ | ✅ | ❌ |
| llm_response_duration_ms | ✅ | ✅ | ❌ |
| user_feedback | ✅ | ❌ (no UI) | ❌ |
| input_type | ✅ | ❌ | ❌ |
| stt_duration_ms | ✅ (voice) | ❌ (N/A) | ❌ |
| voice_duration_s | ✅ (voice) | ❌ (N/A) | ❌ |
| judge_* (3 scores) | ✅ (sampled) | ❌ | ❌ |

**Telegram ↔ FastAPI: 14/14 RAG scores at parity** via shared `_write_langfuse_scores()`.
**Voice Agent: 0 custom scores** — only OTEL auto-spans from LiveKit SDK.

## 4. Deployment Env Vars

| Deploy Target | LANGFUSE_PUBLIC_KEY | LANGFUSE_SECRET_KEY | LANGFUSE_HOST | Gap? |
|---------------|---------------------|---------------------|---------------|------|
| docker-compose.dev.yml → bot | ✅ | ✅ | ✅ | NONE |
| docker-compose.dev.yml → rag-api | ✅ | ✅ | ✅ | NONE |
| docker-compose.dev.yml → voice-agent | ✅ | ✅ | ✅ | NONE |
| docker-compose.dev.yml → litellm | ✅ | ✅ | ✅ | NONE |
| **k8s/base/bot/deployment.yaml** | ❌ | ❌ | ❌ | **HIGH** |

## 5. Gaps Summary (prioritized)

| # | Gap | Severity | Location | Fix |
|---|-----|----------|----------|-----|
| 1 | **k8s deployment missing LANGFUSE_* env vars** | **HIGH** | `k8s/base/bot/deployment.yaml` | Add LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST from secret |
| 2 | **cmd_call — zero Langfuse tracing** | **MEDIUM** | `bot.py:466` | Add `@observe` + `propagate_attributes` + scores |
| 3 | **Voice Agent — no custom Langfuse scores** | **MEDIUM** | `voice/agent.py` | Add call-level scores (stt_duration, call_status) |
| 4 | FastAPI /query — missing judge scores | LOW | `api/main.py:103` | Add `run_online_judge()` like bot |
| 5 | FastAPI /query — missing `input_type` score | LOW | `api/main.py:103` | Add `input_type="api"` score |
| 6 | FastAPI /query — no `@observe` on endpoint | LOW | `api/main.py:103` | `propagate_attributes` creates trace already |
| 7 | cmd_start/help/clear/stats/metrics — no tracing | LOW | `bot.py` | Utility commands, optional |
| 8 | cmd_history — no error span on search failure | LOW | `bot.py:550` | Add `level="ERROR"` in exception handler |
| 9 | transcribe_node — no error span | LOW | `nodes/transcribe.py` | Raises; caught by handle_voice error path |

## 6. Key Findings

1. **Core RAG pipeline: 100% covered.** All 10 graph nodes have `@observe`. 6 heavy nodes have curated spans. 4 nodes have error spans.
2. **Telegram ↔ FastAPI score parity: ACHIEVED** for 14 RAG scores via shared `_write_langfuse_scores()`.
3. **Critical gap: k8s deployment** has zero Langfuse env vars — VPS production bot runs completely blind.
4. **Voice Agent** has OTEL auto-spans from LiveKit but no business-level scores.
5. `handle_feedback` is correct by design — writes `user_feedback` score to existing trace.
