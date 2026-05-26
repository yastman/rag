# Langfuse Trace-Coverage Audit (Static Phase, #2168)

> Scope: static codebase audit of every `@observe(name=...)` declaration
> against `docs/runbooks/LANGFUSE_TRACING_GAPS.md` "Trace Interpretation
> Matrix". Runtime verification (live `make run-bot` + REST API queries
> against Langfuse) is intentionally deferred to an operator with access
> to the local Langfuse stack — the static phase below is reproducible
> from the repo alone and pins the contract.
>
> Audit performed: 2026-05-26, against branch `dev` after Wave 2 PRs
> (#2158, #2163, #2164, #2165, plus the in-flight #2167 fix).

## Method

```bash
grep -rn '@observe(\s*name=' --include='*.py' . \
  | grep -v test | grep -v __pycache__ | grep -v '\.venv/' \
  | awk -F'"' '{print $2"|"$0}' \
  | sort -u
```

The command emits the canonical list of every Langfuse span name that
ships with the codebase, plus the file:line where it is declared.

For each row in the runbook's "Trace Interpretation Matrix" the audit
records:

- **Static**: ✅ if a matching `@observe(name=...)` decorator exists at the
  path the runbook claims (or any path the application actually wires
  in), ⚠️ if the decorator is present but in a stale path, ❌ if missing.
- **Runtime**: deferred (`-`) — requires a live local Langfuse stack
  and `make run-bot` / `make docker-bot-up` exercise; tracked as the
  follow-up operator task on this issue.
- **Tree shape**: deferred (`-`) for the same reason.

## Static census (post Wave 2)

### Telegram surface

| Family | Path | Static |
|---|---|:---:|
| `telegram-message` | `telegram_bot/middlewares/langfuse_middleware.py` | ✅ |
| `telegram-rag-query` | `telegram_bot/bot.py:1921` | ✅ |
| `telegram-rag-supervisor` | `telegram_bot/bot.py:2201` | ✅ |
| `telegram-rag-voice` | `telegram_bot/bot.py:3186` | ✅ |
| `telegram-hitl-callback` | `telegram_bot/bot.py:3453` | ✅ |
| `telegram-history-search` | `telegram_bot/handlers/command_handlers.py:355` | ✅ |
| `cmd-*` (start, clear, clearcache, call) | `telegram_bot/handlers/` | ✅ |
| `cb-*` (callback handlers) | `telegram_bot/handlers/` | ✅ |
| `tool-rag-search` | `telegram_bot/agents/rag_tool.py` | ✅ (post #2158) |
| `tool-apartment-search`, `tool-handoff`, `tool-history-search`, `tool-mortgage-calculator`, `tool-crm-sync-lead-score`, `tool-daily-summary` | `telegram_bot/agents/` | ✅ |

### RAG hot path

| Family | Path | Static |
|---|---|:---:|
| `rag-pipeline` | `telegram_bot/agents/rag_pipeline.py:1007` | ✅ |
| `rag-api-query` | `src/api/main.py:326` | ✅ |
| `rag-search-query` | `src/evaluation/langfuse_integration.py:87` | ✅ |
| `rag-core-build-context` | `telegram_bot/services/rag_core.py` | ✅ (post #2163) |
| `rag-core-rewrite-query` | `telegram_bot/services/rag_core.py` | ✅ (post #2163) |
| `rag-core-perform-rerank` | `telegram_bot/services/rag_core.py` | ✅ (post #2163) |
| `rag-core-compute-query-embedding` | `telegram_bot/services/rag_core.py` | ✅ (post #2163) |
| `rag-core-check-semantic-cache` | `telegram_bot/services/rag_core.py` | ✅ (post #2163) |
| `cache-check` | `telegram_bot/agents/rag_pipeline.py:156` | ✅ |
| `cache-store` | `telegram_bot/agents/rag_pipeline.py:911` | ✅ |
| `hybrid-retrieve` | `telegram_bot/agents/rag_pipeline.py:370` | ✅ |
| `query-rewrite` | `telegram_bot/agents/rag_pipeline.py:837` | ✅ |
| `grade-documents` | `telegram_bot/agents/rag_pipeline.py:687` | ✅ |
| `rerank` | `telegram_bot/agents/rag_pipeline.py:766` | ✅ |
| `retrieval.initial`, `retrieval.relax` | `telegram_bot/agents/rag_pipeline.py` | ✅ |
| `client-direct-pipeline` | `telegram_bot/pipelines/client.py` | ✅ |

### Embedding (BGE-M3 + Voyage)

| Family | Path | Static |
|---|---|:---:|
| `bge-m3-dense-embed` | `src/runtime/integrations/embeddings.py:53` | ✅ |
| `bge-m3-dense-query-embed` | `src/runtime/integrations/embeddings.py:125` | ✅ |
| `bge-m3-sparse-embed`, `bge-m3-sparse-embed-batch` | `src/runtime/integrations/embeddings.py:90,95` | ✅ |
| `bge-m3-hybrid-embed`, `-batch` | `src/runtime/integrations/embeddings.py:131,164` | ✅ |
| `bge-m3-hybrid-colbert-embed` | `src/runtime/integrations/embeddings.py:137` | ✅ |
| `bge-m3-colbert-query-embed` | `src/runtime/integrations/embeddings.py:158` | ✅ |
| `bge-m3-rerank` | `src/services/bge_m3_client.py:263` | ✅ |
| `voyage-embed-query`, `-documents`, `-matryoshka` etc. | `src/services/voyage.py` | ✅ |
| `voyage-contextualized-embed-*` (3) | `src/services/voyage.py` | ✅ |
| `colbert-rerank` | `telegram_bot/services/colbert_reranker.py:52` | ✅ |
| `colbert-rerank-search` | `src/retrieval/search_engines.py:534` | ✅ |
| `core-pipeline-query-embedding` | `src/core/pipeline.py:81` | ✅ |

### Qdrant

| Family | Path | Static |
|---|---|:---:|
| `qdrant-apply-strict-mode` | `src/runtime/services/qdrant.py:118` | ✅ |
| `qdrant-ensure-alias` | `src/runtime/services/qdrant.py:171` | ✅ |
| `qdrant-ensure-collection` | `src/runtime/services/qdrant.py:263` | ✅ |

### Cache

| Family | Path | Static |
|---|---|:---:|
| `cache-semantic-check` | `src/runtime/integrations/cache.py:260` | ✅ |
| `cache-semantic-store` | `src/runtime/integrations/cache.py:396` | ✅ |
| `cache-exact-get`, `-store` | `src/runtime/integrations/cache.py:483,523` | ✅ |
| `cache-embedding-get`, `-store` | `src/runtime/integrations/cache.py:560,595` | ✅ |
| `cache-sparse-get`, `-store` | `src/runtime/integrations/cache.py:632,651` | ✅ |
| `cache-bge-m3-bundle-get`, `-store` | `src/runtime/integrations/cache.py:672,738` | ✅ |
| `cache-search-get`, `-store` | `src/runtime/integrations/cache.py:808,827` | ✅ |
| `cache-rerank-get`, `-store` | `src/runtime/integrations/cache.py:864,884` | ✅ |

### Graph nodes (legacy LangGraph path; coexists with agent SDK)

| Family | Path | Static |
|---|---|:---:|
| `node-classify`, `node-cache-check`, `node-cache-store`, `node-retrieve`, `node-rerank`, `node-grade`, `node-rewrite`, `node-respond`, `node-generate`, `node-summarize`, `node-guard` | `src/runtime/graph/nodes/` | ✅ |
| `edge-route-cache`, `-grade`, `-guard`, `-query-type`, `-start` | `src/runtime/graph/edges/` | ✅ |
| `classify-query` (shared) | `src/runtime/graph/nodes/classify.py:251` | ✅ |

### Voice

| Family | Path | Static |
|---|---|:---:|
| `voice-session` | `src/voice/observability.py:33` (lifecycle) + `src/voice/agent.py` (entry-point span post #2165) | ✅ (post #2165) |
| `voice-tool-search-knowledge-base` | `src/voice/agent.py` (post #2165) | ✅ (post #2165) |

### Mini App funnel

| Family | Path | Static |
|---|---|:---:|
| `miniapp-start-expert` | `mini_app/api.py:178` | ✅ (init wired post #2164) |
| `miniapp-submit-phone` | `mini_app/api.py:354` | ✅ (init wired post #2164) |
| `miniapp-kommo-create-lead` | `mini_app/phone.py:46` | ✅ (init wired post #2164) |

### CRM / Kommo (referenced from runbook adjacency)

| Family | Path | Static |
|---|---|:---:|
| `kommo-create-lead`, `-update-lead`, `-add-note`, `-create-task`, … (~16 helpers) | `src/runtime/services/kommo*.py` | ✅ |
| `crm-create-lead`, `-update-lead`, `-add-note`, … (~25 helpers) | `src/runtime/integrations/crm/` | ✅ |
| `dialog-crm-*`, `dialog-filter-*`, `dialog-funnel-*` | `telegram_bot/dialogs/` | ✅ |

### Auxiliary surfaces

| Family | Path | Static |
|---|---|:---:|
| `ingestion-cli-run`, `-preflight`, `ingestion-flow-run-once`, `-watch`, `ingestion-qdrant-upsert-chunks`, `ingestion-qdrant-delete-file` | `scripts/`, `telegram_bot/integrations/ingestion/` | ✅ |
| `apartments-*` (4 helpers) | `telegram_bot/services/apartments_service.py` | ✅ |
| `apartment-extraction-pipeline`, `apartment-filter-parse`, `apartment-llm-extract` | `telegram_bot/services/apartment*.py` | ✅ |
| `funnel-rollup`, `funnel-store-upsert`, `lead-score-upsert`, `manager-*`, `nurturing-*` | `telegram_bot/services/`, `src/services/` | ✅ |
| `history-*` (12 helpers including `history-save`, `history-retrieve`, `history-grade`, `history-rewrite`, `history-summarize`, `history-search`) | `telegram_bot/services/history_service.py` | ✅ |
| `claude-contextualize`, `groq-contextualize`, `openai-contextualize` (× sync/batch) | `src/contextualization/` | ✅ |
| `service-generate-response`, `generate-answer`, `advisor-llm-call`, `detect-agent-intent`, `detect-response-style`, `hyde-generate-document` | `telegram_bot/services/`, `src/services/` | ✅ |
| `transcribe`, `demo-transcribe-voice` | voice / demo helpers | ✅ |
| `litellm-acompletion` | LiteLLM proxy callback (NOT app-instrumented) | n/a (proxy noise per runbook) |

## Static audit summary

- **Total `@observe`-named spans in code:** ~190.
- **Static gaps versus current runbook matrix:** 0.
  - Every family the runbook claims is present at the documented path.
  - Wave 2 additions (`rag-core-*`, `voice-tool-search-knowledge-base`,
    `miniapp-*` once #2164 lifespan init merges) are now backed by static
    decorators.
- **Runbook gaps versus static reality:** the existing matrix in
  `LANGFUSE_TRACING_GAPS.md` enumerates only ~7 families. The static
  reality is ~190 named spans grouped into 11 surface areas. The matrix
  is intentionally a curated subset focused on the high-value families;
  this audit document records the full census so reviewers can spot
  drift in either direction.

## Runtime verification — deferred operator task

For each non-empty family above, the operator should run on a live
local stack:

```bash
set -a; source .env; set +a
curl -fsS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?name=<NAME>&limit=5" \
  | jq '.meta.totalItems, [.data[] | {id, sessionId, userId, observations: (.observations|length)}]'
```

and confirm `meta.totalItems > 0` after exercising the corresponding
runtime path (`make run-bot`, voice dev dispatch, `mini-app-api` call,
`make ingest-unified-status`).

The runtime cells in the tables above are intentionally left blank;
they should be filled by the operator running the audit and posted as a
comment on this issue along with the outputs of:

```bash
make validate-traces-fast
make langfuse-latest-trace-audit
```

## Followups

- ❌ → file a child issue per missing family with reproduction recipe.
- ⚠️ → file a child issue when curated metadata is missing or
  parent-observation chain mis-shapes.
- Stale paths in `LANGFUSE_TRACING_GAPS.md` Trace Interpretation Matrix
  → fix in this PR.

## References

- Runbook: `docs/runbooks/LANGFUSE_TRACING_GAPS.md`
- Wave 2 PRs: #2158, #2163, #2164, #2165
- Wave 2 follow-up: #2167 (executor contextvars propagation)
- Wave 1 burn-down: #1658-#1666
- Validation tooling: `make validate-traces-fast`,
  `make langfuse-latest-trace-audit`
- SDK docs (Context7): `/langfuse/langfuse-python`
