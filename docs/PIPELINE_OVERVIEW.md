# Pipeline Overview

> Operational overview of ingestion, query, and voice flows. The core text RAG path is procedural via `src.core.run_assistant_request()` → `src.runtime.pipeline.run_assistant_pipeline()` (ADR-0019). Telegram/voice adapters use `create_agent` for conversational shell behavior. See [`CLIENT_PIPELINE.md`](CLIENT_PIPELINE.md) and [`docs/adr/0019-core-text-path-procedural-runtime.md`](adr/0019-core-text-path-procedural-runtime.md) for implementation detail.

Operational overview of ingestion, query, and voice flows.

## 1) Query Pipeline (Telegram Bot / API)

The bot has **two paths** for queries (see [`CLIENT_PIPELINE.md`](CLIENT_PIPELINE.md) for full details):

- **Core text path** is procedural via `src.core.run_assistant_request()` → `src.runtime.pipeline.run_assistant_pipeline()` (ADR-0019). This is the canonical product path.
- **Telegram adapter** uses `create_agent` for conversational shell behavior (streaming, tools, history trimming). It calls `run_assistant_request()` for product RAG.
- **Voice path** uses `build_graph()` from the compat façade ([`telegram_bot/graph/graph.py`](../telegram_bot/graph/graph.py)), which wraps `run_assistant_pipeline()` — **not** an active StateGraph (ARCH-16 decision, #2697). Voice is an optional surface (removed in #2791).

The node list below describes the **voice-path façade stages** and the inner stages reused by the text path's `rag_search` tool. Routing rules and conditional edges between these nodes live in [`PIPELINE_ROUTING.md`](PIPELINE_ROUTING.md).

Main nodes:
- `transcribe` (voice input only)
- `classify`
- `guard` (content filtering)
- `cache_check`
- `retrieve`
- `grade`
- `rerank`
- `rewrite`
- `generate`
- `cache_store`
- `respond`
- optional `summarize` (when checkpointer is enabled)

High-level flow:

```text
START -> (transcribe?) -> classify ->
  - chitchat/off-topic: respond -> END
  - otherwise: guard -> cache_check ->
      - cache hit: respond -> END
      - miss: retrieve -> grade ->
          - rerank or rewrite or generate -> cache_store -> respond -> (summarize?) -> END
```

## 2) Retrieval Flow

- Dense embedding: BGE-M3 API (`/encode/dense`)
- Sparse embedding: BGE-M3 API (`/encode/sparse`)
- Qdrant hybrid search (`dense` + `bm42`)
- Optional ColBERT-style rerank path via BGE-M3 API
- Runtime integrations live in `telegram_bot/integrations/` and `telegram_bot/services/`

## 3) Ingestion Flow (Unified)

Source code: `src/ingestion/unified/`.

Flow stages:
1. Watch/read files from `GDRIVE_SYNC_DIR` via CocoIndex `LocalFile` source.
2. Build stable `file_id` from manifest (content-hash aware).
3. Parse and chunk documents via Docling.
4. Generate embeddings (local BGE-M3 by default; Voyage path still supported).
5. Upsert/delete chunks in Qdrant through custom target connector.
6. Track processing status and DLQ state in PostgreSQL.

CLI:

```bash
uv run python -m src.ingestion.unified.cli --help
uv run python -m src.ingestion.unified.cli preflight
uv run python -m src.ingestion.unified.cli bootstrap
uv run python -m src.ingestion.unified.cli run --watch
uv run python -m src.ingestion.unified.cli status
```

Common operator entrypoints:

```bash
make ingest-unified-status
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified
make ingest-unified-watch
make ingest-unified-status
```

## 4) Voice Flow

Source code: `archive/voice/agent.py` + `archive/api/main.py`. This is an archived optional surface; off by default.

Runtime path:
1. LiveKit session starts voice agent.
2. `/call` dispatch metadata carries `langfuse_trace_id` for continuity.
3. Voice agent calls RAG API (`POST /query`) with the same `langfuse_trace_id`.
4. RAG API runs the same graph pipeline used by Telegram bot.
5. Transcript persistence goes to PostgreSQL when configured.

## 5) Observability

- Structured product logs are the required observability surface (`src/utils/product_events.py`).
- Optional Langfuse traces/scores: `telegram_bot/observability.py`, scoring hooks in `src/evaluation/`.
- Log monitoring: Loki + Promtail + Alertmanager (optional `obs` profile).
- Alert rules: `docker/monitoring/rules/*.yaml`.

## 6) Main Operational Commands

```bash
make docker-up
make docker-bot-up
make ingest-unified-status
make ingest-unified-preflight
make ingest-unified-bootstrap
make ingest-unified
make e2e-core-live
# monitoring-up (obs stack) archived — see archive/obs/
```
