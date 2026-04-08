# RAG API Reference

FastAPI service wrapping the LangGraph pipeline for external query execution.

**Entry point:** `src/api/main.py`
**Port:** 8080 (production via Docker), 8000 (dev via uvicorn)

## Endpoints

### `GET /health`

Readiness probe. Returns immediately without checking downstream services.

**Response:**
```json
{ "status": "ok" }
```

---

### `POST /query`

Execute a RAG query through the full LangGraph pipeline.

**Request body:** `QueryRequest`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | User query text (1–4096 chars) |
| `user_id` | int | 0 | Optional user identifier |
| `session_id` | string | "" | Optional session identifier |
| `channel` | string | "api" | Source channel: `api`, `voice`, `telegram` |
| `langfuse_trace_id` | string | null | Optional Langfuse trace ID for cross-trace linking |

**Response:** `QueryResponse`

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Generated answer |
| `query_type` | string | Classified query type (e.g., `APARTMENT`, `KNOWLEDGE`, `CHITCHAT`) |
| `cache_hit` | bool | Whether semantic cache was hit |
| `documents_count` | int | Number of retrieved documents |
| `rerank_applied` | bool | Whether reranking was applied |
| `latency_ms` | float | Total pipeline latency in milliseconds |
| `context` | list[dict] | Retrieved context documents (for evaluation) |

**Example request:**
```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the requirements for permanent residency?",
    "user_id": 12345,
    "channel": "api"
  }'
```

**Example response:**
```json
{
  "response": "Permanent residency in Bulgaria requires...",
  "query_type": "KNOWLEDGE",
  "cache_hit": false,
  "documents_count": 5,
  "rerank_applied": true,
  "latency_ms": 847.3,
  "context": [
    {"id": "doc-123", "text": "...", "score": 0.92},
    {"id": "doc-456", "text": "...", "score": 0.88}
  ]
}
```

---

## Error Responses

| Status | Body | Cause |
|--------|------|-------|
| 422 | Validation error | Invalid request body |
| 500 | `{"error": "Internal server error"}` | Unhandled exception |

For 500 errors, check Langfuse traces for the corresponding `rag-api-query` trace.

---

## Architecture

```
POST /query
    ↓
FastAPI lifespan initializes:
  - GraphConfig.from_env()
  - CacheLayerManager (Redis)
  - QdrantService
  - Embeddings (BGE-M3)
  - LLM (via LiteLLM)
    ↓
build_graph() from telegram_bot/graph/graph.py
    ↓
ainvoke() with RAGState
    ↓
Returns QueryResponse with context
```

---

## Observability

- Trace family: `rag-api-query`
- Langfuse scores written via `write_langfuse_scores()`
- `langfuse_trace_id` propagation for cross-trace linking with voice sessions

---

## Running Locally

```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080
# Or via make:
make docker-bot-up
```
