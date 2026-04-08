# RAG API Reference

The RAG API exposes a FastAPI endpoint for running RAG queries through the LangGraph pipeline.

## Base URL

```
http://localhost:8080  # Local development
http://rag-api:8080   # Docker Compose
```

## Endpoints

### POST /query

Run a RAG query through the LangGraph pipeline.

**Request:**

```json
{
  "query": "string",           // Required: User query text (1-4096 chars)
  "user_id": 0,                // Optional: User identifier
  "session_id": "string",      // Optional: Session identifier (defaults to "api-{user_id}")
  "channel": "api",            // Optional: Source channel (api, voice, telegram)
  "langfuse_trace_id": "string" // Optional: Langfuse trace ID for linking
}
```

**Response:**

```json
{
  "response": "string",          // Generated answer
  "query_type": "string",        // Classified query type
  "cache_hit": false,            // Whether semantic cache was hit
  "documents_count": 0,          // Number of retrieved documents
  "rerank_applied": false,       // Whether reranking was applied
  "latency_ms": 0.0,            // Total pipeline latency in milliseconds
  "context": []                  // Retrieved context documents
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

### Current Behavior (Generic)

The API currently returns generic errors for all failures:

```json
{
  "error": "Internal server error"
}
```

**Status codes:**
- `500 Internal Server Error` — For all unhandled exceptions

### Recommended: Structured Errors

For better API consumer experience, consider implementing structured errors:

**Proposed error response format:**

```json
{
  "error": "error_code",           // Machine-readable error code
  "message": "Human-readable message",
  "trace_id": "abc-123-def",       // For log correlation
  "recoverable": true               // Whether retry might help
}
```

**Error code recommendations:**

| Error Code | HTTP Status | Description | Recoverable |
|------------|-------------|-------------|-------------|
| `validation_error` | 400 | Invalid request parameters | No |
| `query_too_long` | 400 | Query exceeds 4096 chars | No |
| `invalid_session_id` | 400 | Malformed session ID | No |
| `qdrant_unavailable` | 503 | Vector DB unreachable | Yes |
| `redis_unavailable` | 503 | Cache service down | Yes |
| `llm_timeout` | 504 | LLM request timed out | Yes |
| `rate_limited` | 429 | Too many requests | Yes |

## Request/Response Schemas

### QueryRequest

```python
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    user_id: int = Field(default=0)
    session_id: str = Field(default="")
    channel: str = Field(default="api")
    langfuse_trace_id: str | None = Field(default=None)
```

### QueryResponse

```python
class QueryResponse(BaseModel):
    response: str
    query_type: str = ""
    cache_hit: bool = False
    documents_count: int = 0
    rerank_applied: bool = False
    latency_ms: float = 0.0
    context: list[dict[str, Any]] = []
```

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

For full dependency health checks, use the preflight command:

```bash
make preflight
```

## Langfuse Tracing

All queries are traced in Langfuse with:
- **Trace family:** `rag-api-query`
- **Tags:** `["api", "rag", "{channel}"]`
- **Metadata:** `query_type`, `source`

## Related Documentation

- [Pipeline Overview](PIPELINE_OVERVIEW.md)
- [Observability](../.claude/rules/features/telegram-bot.md#observability)
