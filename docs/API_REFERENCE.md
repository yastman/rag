# API Reference

Quick reference for calling the RAG API. [`RAG_API.md`](RAG_API.md) is the canonical request/response contract and owns field-level schema details.

## Base URL

```
http://localhost:8080  # Local development
http://rag-api:8080   # Docker Compose
```

## Endpoints

### POST /query

Run a RAG query through the LangGraph pipeline.

Minimal request:

```json
{
  "query": "What documents are needed for buying property?",
  "user_id": 12345,
  "channel": "api"
}
```

Response shape is `QueryResponse`; see [`RAG_API.md`](RAG_API.md#post-query) for the full schema. Current `query_type` values are `CHITCHAT`, `OFF_TOPIC`, `STRUCTURED`, `FAQ`, `ENTITY`, and `GENERAL`.

```json
{
  "response": "string",
  "query_type": "string",
  "cache_hit": false,
  "documents_count": 0,
  "rerank_applied": false,
  "latency_ms": 0.0,
  "context": []
}
```

**Example:**

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What apartments are available in Sochi?",
    "user_id": 12345,
    "session_id": "session-abc",
    "channel": "api"
  }'
```

### GET /health

Readiness probe for the RAG API.

**Response:**

```json
{
  "status": "ok"
}
```

## Error Responses

Unhandled exceptions return the structured shape implemented in `src/api/main.py`:

```json
{
  "error": "internal_error",
  "message": "Internal server error",
  "trace_id": "abc123...",
  "recoverable": false
}
```

Validation errors use FastAPI/Pydantic's standard 422 response. `GraphRecursionError` is handled inside `/query` as a successful `QueryResponse` with `query_type: "ERROR"` and a fallback user response.

## Request/Response Schemas

The Pydantic models live in `src/api/schemas.py`. Field-level documentation is maintained in [`RAG_API.md`](RAG_API.md#post-query).

## Integration Examples

### Python (httpx)

```python
import httpx

async def query_rag(question: str, user_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/query",
            json={
                "query": question,
                "user_id": user_id,
                "channel": "api",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
```

### Voice Agent Integration

The voice agent calls RAG API via `httpx`:

```python
async def search_knowledge_base(query: str, trace_id: str | None = None) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RAG_API_URL}/query",
            json={
                "query": query,
                "channel": "voice",
                "langfuse_trace_id": trace_id,
            },
            timeout=30.0,
        )
        data = response.json()
        return data["response"]
```

## Rate Limits

No rate limiting is currently enforced on the RAG API.

## Health Check Semantics

The `/health` endpoint checks:
- FastAPI application is running
- Does NOT check: Redis, Qdrant, BGE-M3, LLM availability

For local bot/runtime dependency checks, use the local development preflight:

```bash
make test-bot-health
```

The RAG API also initializes Redis, Qdrant, embeddings, and LLM clients in FastAPI lifespan startup. A successful `/health` response is therefore a cheap liveness/readiness signal for the app process, not a deep dependency probe.

## Langfuse Tracing

All queries are traced in Langfuse with:
- **Trace family:** `rag-api-query`
- **Tags:** `["api", "rag", "{channel}"]`
- **Metadata:** `query_type`, `source`

## Related Documentation

- [RAG API Contract](RAG_API.md)
- [Pipeline Overview](PIPELINE_OVERVIEW.md)
- [Bot Architecture](BOT_ARCHITECTURE.md)
