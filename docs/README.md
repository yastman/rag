# Documentation Hub

Navigation map for the RAG Q&A chatbot. This page links **only to docs that exist**;
it is the target of the `docs/README.md` reference in [`AGENTS.md`](../AGENTS.md) and
[`README.md`](../README.md).

> Planning state (roadmap, phases, todo/decision cards) does **not** live here — it lives
> in the **codeindexer** memory store. Start a session with `briefing(project="rag-fresh")`.

## Start here

| You want… | Read |
|---|---|
| What this is, features, the spine | [`../README.md`](../README.md) |
| Agent/onboarding gateway | [`../AGENTS.md`](../AGENTS.md) |
| Runtime, Compose, ports, env, deploy | [`../DOCKER.md`](../DOCKER.md) |
| Contributing workflow | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Security policy | [`../SECURITY.md`](../SECURITY.md) · Code of conduct: [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) |
| Change history | [`../CHANGELOG.md`](../CHANGELOG.md) |

## The spine (the one flow worth memorising)

```
run_assistant_request        src/core/assistant.py
  → run_assistant_pipeline   src/runtime/pipeline/assistant_pipeline.py
    → classify_query
    → rag_pipeline           src/runtime/pipeline/rag.py   (cache → hybrid search → grade → rerank → optional rewrite loop)
    → generate_answer        src/runtime/generation/service.py
```

Layering (enforced by `import-linter`, see [`../pyproject.toml`](../pyproject.toml) `[tool.importlinter]`):
`src/core` → `src/runtime` → `telegram_bot`. Inner layers must not import outer ones.

## Engine — `src/`

| Area | README |
|---|---|
| Overview | [`../src/README.md`](../src/README.md) |
| Public boundary (DI contracts + entrypoint) | [`../src/core/README.md`](../src/core/README.md) |
| Pipeline / RAG / retrieval / generation engine | [`../src/runtime/README.md`](../src/runtime/README.md) |
| HTTP API | [`../src/api/README.md`](../src/api/README.md) |
| Config / settings | [`../src/config/README.md`](../src/config/README.md) |
| Retrieval | [`../src/retrieval/README.md`](../src/retrieval/README.md) |
| Ingestion (overview · unified · apartments) | [`../src/ingestion/README.md`](../src/ingestion/README.md) · [`../src/ingestion/unified/AGENTS.override.md`](../src/ingestion/unified/AGENTS.override.md) · [`../src/ingestion/apartments/README.md`](../src/ingestion/apartments/README.md) |
| Contextualization · models · utils · security | [`../src/contextualization/README.md`](../src/contextualization/README.md) · [`../src/models/README.md`](../src/models/README.md) · [`../src/utils/README.md`](../src/utils/README.md) · [`../src/security/README.md`](../src/security/README.md) |

## Adapter — `telegram_bot/`

| Area | README |
|---|---|
| Overview · local rules | [`../telegram_bot/README.md`](../telegram_bot/README.md) · [`../telegram_bot/AGENTS.override.md`](../telegram_bot/AGENTS.override.md) |
| Handlers · agents · dialogs · services | [`../telegram_bot/handlers/README.md`](../telegram_bot/handlers/README.md) · [`../telegram_bot/agents/README.md`](../telegram_bot/agents/README.md) · [`../telegram_bot/dialogs`](../telegram_bot/dialogs) · [`../telegram_bot/services/README.md`](../telegram_bot/services/README.md) |
| Integrations · pipelines · keyboards · middlewares | [`../telegram_bot/integrations/README.md`](../telegram_bot/integrations/README.md) · [`../telegram_bot/pipelines/README.md`](../telegram_bot/pipelines/README.md) · [`../telegram_bot/keyboards/README.md`](../telegram_bot/keyboards/README.md) · [`../telegram_bot/middlewares/README.md`](../telegram_bot/middlewares/README.md) |
| Constants · config · models · locales | [`../telegram_bot/constants/README.md`](../telegram_bot/constants/README.md) · [`../telegram_bot/config/README.md`](../telegram_bot/config/README.md) · [`../telegram_bot/models/README.md`](../telegram_bot/models/README.md) · [`../telegram_bot/locales/README.md`](../telegram_bot/locales/README.md) |

## Sidecar services & infra

| Area | README |
|---|---|
| Services overview · local rules | [`../services/README.md`](../services/README.md) · [`../services/AGENTS.override.md`](../services/AGENTS.override.md) |
| BGE-M3 embeddings API | [`../services/bge-m3-api/README.md`](../services/bge-m3-api/README.md) · [`../services/bge-m3-api/AGENTS.override.md`](../services/bge-m3-api/AGENTS.override.md) |
| Docling parsing | [`../services/docling/README.md`](../services/docling/README.md) · [`../services/docling/AGENTS.override.md`](../services/docling/AGENTS.override.md) |
| Docker / Compose assets | [`../docker/README.md`](../docker/README.md) · [`../docker/ingestion/README.md`](../docker/ingestion/README.md) · [`../docker/postgres/README.md`](../docker/postgres/README.md) |

## Tests, scripts, audits

| Area | README |
|---|---|
| Test pyramid + tier→command map | [`../tests/README.md`](../tests/README.md) |
| Scripts · local rules · E2E helpers | [`../scripts/README.md`](../scripts/README.md) · [`../scripts/AGENTS.override.md`](../scripts/AGENTS.override.md) · [`../scripts/e2e/README.md`](../scripts/e2e/README.md) |
| Audits | [`audits/runtime-infra-config-audit-2026-06.md`](audits/runtime-infra-config-audit-2026-06.md) |

## Known gaps (tracked, not yet written)

Several historical guides under `docs/engineering/`, `docs/runbooks/`, and top-level
`docs/*.md` (LOCAL-DEVELOPMENT, INGESTION, QDRANT_STACK, HITL, …) are referenced by older
READMEs but were removed in a docs cleanup and are **not yet restored**. The restore-vs-descope
decision and the dead-link repair are tracked on the roadmap (codeindexer phase
"P16 · Documentation & navigation"). Until then, this hub is the source of truth for what exists.
