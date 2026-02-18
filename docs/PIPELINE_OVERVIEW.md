# Pipeline Overview

Operational overview of ingestion, query, and voice flows.

## 1) Query Pipeline (Telegram Bot / API)

`telegram_bot/graph/graph.py` builds a LangGraph state machine.

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

## 4) Voice Flow

Source code: `src/voice/agent.py` + `src/api/main.py`.

Runtime path:
1. LiveKit session starts voice agent.
2. Voice agent calls RAG API (`POST /query`).
3. RAG API runs the same graph pipeline used by Telegram bot.
4. Transcript persistence goes to PostgreSQL when configured.

## 5) Observability

- App traces/scores: Langfuse (`telegram_bot/observability.py`, scoring hooks)
- Log monitoring: Loki + Promtail + Alertmanager
- Alert rules: `docker/monitoring/rules/*.yaml`

## 6) Main Operational Commands

```bash
make docker-up
make docker-bot-up
make ingest-unified
make validate-traces-fast
make monitoring-up
```
