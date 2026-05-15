# Project Guide

This guide is for reviewers who need to understand the repository quickly
without reading every file. It complements the portfolio summary in
`docs/portfolio/resume-case-study.md`.

## What This Project Is

Conversational AI automation platform with:

- Telegram bot workflows for clients and managers
- contextual RAG over private/domain knowledge
- natural-language domain catalog search
- Kommo CRM automation and lead scoring
- Telegram voice input and LiveKit voice-agent path
- unified document ingestion into Qdrant
- Langfuse tracing, scoring, prompt management, and evaluation tooling
- Docker Compose based local/VPS runtime

## Recommended Reading Path

**10 minutes:** `README.md` → `docs/portfolio/resume-case-study.md` → skim this guide.

**30 minutes:** add `telegram_bot/graph/`, `telegram_bot/agents/`, and
`telegram_bot/services/`.

**Deep dive:** add `src/ingestion/unified/`, `src/voice/`, `compose*.yml`,
`DOCKER.md`, and the test directories.

Ordered list for sequential reading:

1. `README.md` for the project overview and architecture diagram.
2. `docs/portfolio/resume-case-study.md` for the resume-style narrative.
3. `telegram_bot/graph/` for LangGraph routing and state contracts.
4. `telegram_bot/agents/` for CRM tools, HITL, history search, and agent setup.
5. `telegram_bot/services/` for business logic, cache, Kommo, catalog search,
   lead scoring, and handoff services.
6. `src/ingestion/unified/` for ingestion determinism, state, DLQ, and Qdrant writes.
7. `src/voice/` for LiveKit voice agent and shared RAG API integration.
8. `compose.yml`, `compose.dev.yml`, and `DOCKER.md` for runtime architecture.

## Folder Map

### `telegram_bot/`

Main Telegram product surface. Contains aiogram handlers, dialog flows,
middlewares, LangGraph orchestration, CRM/agent integrations, localization,
and bot startup/preflight logic.

### `telegram_bot/graph/`

LangGraph RAG runtime: state, nodes, conditional edges, cache/retrieval/rerank/
generation flow, and routing contracts.

### `telegram_bot/agents/`

Agent-facing tools and orchestration: CRM tools, domain/catalog tools, HITL
interrupts, history search, and agent factory/prompt wiring.

### `telegram_bot/services/`

Business services and integration logic: catalog search/filtering, Kommo
client, lead scoring, handoff state, cache behavior, hot-lead notifications,
and RAG service helpers.

### `telegram_bot/dialogs/` and `telegram_bot/handlers/`

User and manager interaction layer: menus, catalog, viewing flow, CRM task
dialogs, phone collection, handoff, and command/message handlers.

### `src/ingestion/unified/`

Unified ingestion pipeline: Google Drive/local file identity, Docling parsing,
chunking, manifest/state handling, Qdrant writes, retries, and DLQ behavior.

### `src/voice/`

LiveKit voice agent path, transcript persistence, RAG API client, SIP setup,
and voice observability helpers.

### `mini_app/`

Telegram Mini App backend and frontend. Treat this as a lightweight entry
surface, not full parity with the Telegram bot.

### `services/`

Local service containers and helper APIs, including BGE-M3 and USER2-base
embedding services.

### `compose*.yml`, `docker/`, `DOCKER.md`

Docker Compose runtime. Compose is the primary local/VPS operating path. k3s
manifests exist separately but are not full parity with the Compose service set.

### `k8s/`

Partial k3s manifests for core services. Use conservative wording when
describing k3s support.

### `tests/`

Unit, contract, integration, smoke, evaluation, and baseline tests. Local
verification is the release authority; CI is intentionally lighter.

### `docs/`

Architecture docs, runbooks, engineering notes, test-writing guidance, SDK
registry, and portfolio material.

## High-Signal Files

- `telegram_bot/graph/graph.py`
- `telegram_bot/graph/state.py`
- `telegram_bot/agents/crm_tools.py`
- `telegram_bot/agents/hitl.py`
- `telegram_bot/services/filter_extractor.py`
- `telegram_bot/services/qdrant.py`
- `telegram_bot/integrations/cache.py`
- `telegram_bot/scoring.py`
- `telegram_bot/integrations/prompt_manager.py`
- `src/ingestion/unified/cli.py`
- `src/ingestion/unified/state_manager.py`
- `src/voice/agent.py`
- `compose.yml`
- `DOCKER.md`

## Honest Scope Notes

- Docker Compose is the primary runtime path; k3s is partial.
- Loki/Alertmanager are local/dev monitoring unless production evidence is
  added.
- HITL applies to CRM write operations, not every possible state transition.
- The Mini App is a lightweight entry point and not full catalog-search parity.
- Some i18n migration work remains because not every user-facing string is in
  Fluent files.
