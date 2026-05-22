# API Quick-Start Guide

Integration examples for calling the RAG API. This page owns curl/httpx recipes and deployment URLs. For the full contract (field definitions, error shapes, schema details), see [`RAG_API.md`](RAG_API.md).

## Base URL

| Environment | URL |
|---|---|
| Local development | `http://localhost:8080` |
| Docker Compose (inter-service) | `http://rag-api:8080` |

---

## Examples

### Health Check

```bash
# Shallow (liveness)
curl -fsS http://localhost:8080/health

# Deep (readiness -- probes Redis and Qdrant)
curl -fsS "http://localhost:8080/health?deep=true"
```

### Query (curl)

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

### Query (Python / httpx)

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

The voice agent calls the RAG API via `httpx` with cross-trace linking:

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

---

## Rate Limits

No rate limiting is currently enforced on the RAG API.

---

## Related Documentation

- [RAG API Contract](RAG_API.md) -- full schema, error model, architecture
- [Error Response Taxonomy](ERROR_RESPONSES.md) -- system-wide error reference
- [Pipeline Overview](PIPELINE_OVERVIEW.md) -- end-to-end pipeline flows
- [Bot Architecture](BOT_ARCHITECTURE.md) -- Telegram bot layer
