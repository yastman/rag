# RAG API Contract

FastAPI service wrapping the LangGraph pipeline for external query execution.

**Entry point:** `src/api/main.py`
**Port:** 8080 (production via Docker), 8000 (dev via uvicorn)

This page is the canonical owner of the API contract: endpoints, request/response schemas, error model, and deployment surface. For integration examples (curl, httpx, voice agent), see [`API_REFERENCE.md`](API_REFERENCE.md).

## Endpoints

### `GET /health`

Readiness probe. Returns immediately without checking downstream services.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `deep` | bool | false | When true, probes cache and Qdrant; returns 503 if any dependency is unhealthy |

**Shallow response (default):**
```json
{ "status": "ok" }
```

**Deep response (`?deep=true`):**
```json
{
  "status": "ok",
  "components": {
    "cache": { "status": "ok" },
    "qdrant": { "status": "ok" }
  }
}
```

Returns HTTP 503 with `"status": "degraded"` if any component is unhealthy.

---

### `POST /query`

Execute a RAG query through the full LangGraph pipeline.

**Request body:** `QueryRequest` (defined in `src/api/schemas.py`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | User query text (1-4096 chars) |
| `user_id` | int | 0 | Optional user identifier |
| `session_id` | string | "" | Optional session identifier |
| `channel` | string | "api" | Source channel: `api`, `voice`, `telegram` |
| `langfuse_trace_id` | string | null | Optional Langfuse trace ID for cross-trace linking |

**Response:** `QueryResponse` (defined in `src/api/schemas.py`)

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Generated answer |
| `query_type` | string | Classified query type (see values below) |
| `cache_hit` | bool | Whether semantic cache was hit |
| `documents_count` | int | Number of retrieved documents |
| `rerank_applied` | bool | Whether reranking was applied |
| `latency_ms` | float | Total pipeline latency in milliseconds |
| `context` | list[dict] | Retrieved context documents (for evaluation) |

`query_type` values come from `telegram_bot/graph/nodes/classify.py`: `CHITCHAT`, `OFF_TOPIC`, `STRUCTURED`, `FAQ`, `ENTITY`, `GENERAL`, plus `ERROR` for recursion-limit fallback.

---

## Error Model

All error responses share a consistent envelope shape with a `trace_id` for log correlation. The `trace_id` is the current Langfuse trace ID when available; otherwise the handler generates a UUID hex string.

For the full system-wide error taxonomy, see [`ERROR_RESPONSES.md`](ERROR_RESPONSES.md).

### 422 -- Validation Error

Returned when the request body fails Pydantic validation.

```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "details": [
    {
      "loc": ["body", "query"],
      "msg": "String should have at least 1 character",
      "type": "string_too_short"
    }
  ],
  "trace_id": "abc123...",
  "recoverable": true
}
```

### 4xx -- HTTP Errors

Returned for routing/auth errors (404, 401, 403, etc.).

```json
{
  "error": "http_error",
  "message": "Not Found",
  "status_code": 404,
  "trace_id": "abc123...",
  "recoverable": true
}
```

### 500 -- Internal Error

Returned for unhandled exceptions.

```json
{
  "error": "internal_error",
  "message": "Internal server error",
  "trace_id": "abc123...",
  "recoverable": false
}
```

For 500 errors, search Langfuse for the corresponding `rag-api-query` trace using the `trace_id`.

### GraphRecursionError Handling

`GraphRecursionError` is caught inside `/query` and returns a successful `QueryResponse` (HTTP 200) with `query_type: "ERROR"` and a fallback user response -- it does not surface as an HTTP error.

---

## Architecture

```
POST /query
    |
FastAPI lifespan initializes:
  - GraphConfig.from_env()
  - CacheLayerManager (Redis)
  - QdrantService
  - Embeddings (BGE-M3)
  - LLM (via LiteLLM)
    |
build_graph() from telegram_bot/graph/graph.py
    |
ainvoke() with RAGState
    |
Returns QueryResponse with context
```

---

## Observability

- Trace family: `rag-api-query`
- Tags: `["api", "rag", "{channel}"]`
- Langfuse scores written via `write_langfuse_scores()`
- `langfuse_trace_id` propagation for cross-trace linking with voice sessions

---

## Running Locally

```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080
# Or via make:
make docker-voice-up
```
