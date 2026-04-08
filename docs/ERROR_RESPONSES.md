***REMOVED*** Error Response Reference

Standardized error responses across the system.

***REMOVED******REMOVED*** Telegram Bot Errors

***REMOVED******REMOVED******REMOVED*** Handler Errors

Errors in message/callback handlers are caught by `setup_error_handler` middleware and returned as user-friendly messages.

```python
***REMOVED*** telegram_bot/middlewares/error_handler.py
async def error_handler(event, next):
    try:
        return await next(event)
    except Exception as e:
        ***REMOVED*** Send user-friendly message
        await event.reply(f"⚠️ Error: {get_user_message(e)}")
        ***REMOVED*** Re-raise for logging
        raise
```

***REMOVED******REMOVED******REMOVED*** User-Facing Error Messages

| Error Type | User Message | Technical Details |
|------------|--------------|-------------------|
| `RedisConnectionError` | "Service temporarily unavailable" | Logged, not shown |
| `QdrantTimeout` | "Search timed out, try again" | Logged |
| `LLMError` | "AI service error, try again" | Traced in Langfuse |
| `ValidationError` | "Invalid input" | Logged |
| `Unauthorized` | "Please start over: /start" | FSM reset |

***REMOVED******REMOVED******REMOVED*** FSM Errors

| Error | Cause | Recovery |
|-------|-------|----------|
| `FSMConflictError` | Concurrent updates | Retry with fresh state |
| `StateNotFound` | Redis key expired | `/start` to re-init |
| `FSMCancelError` | User sent `/cancel` | Normal flow |

***REMOVED******REMOVED*** RAG API Errors

***REMOVED******REMOVED******REMOVED*** HTTP Status Codes

| Status | Meaning | Response Body |
|--------|---------|---------------|
| 200 | Success | `QueryResponse` |
| 422 | Validation error | `{"detail": [...]}` |
| 500 | Internal error | `{"error": "Internal server error"}` |

***REMOVED******REMOVED******REMOVED*** Error Response Schema

```python
class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    trace_id: str | None = None  ***REMOVED*** Langfuse trace ID for debugging
```

***REMOVED******REMOVED******REMOVED*** Langfuse Trace Linking

500 errors include `trace_id` in response for debugging:

```json
{
  "error": "Internal server error",
  "trace_id": "abc123-def456"
}
```

Search Langfuse UI for this trace ID.

***REMOVED******REMOVED*** Graph Pipeline Errors

***REMOVED******REMOVED******REMOVED*** Node-Level Errors

Errors in nodes are caught and logged but don't crash the graph:

```python
@observe(name="node-retrieve")
async def retrieve_node(state, context):
    try:
        return await _do_retrieval(state)
    except Exception as e:
        logger.exception("Retrieval failed")
        return {"error": str(e), "retrieve_failed": True}
```

***REMOVED******REMOVED******REMOVED*** Graceful Degradation

| Node Failure | Behavior |
|--------------|----------|
| `retrieve` | Proceed without context, use LLM knowledge |
| `rerank` | Skip reranking, use raw retrieval order |
| `generate` | Return error message |
| `cache_check` | Bypass cache, proceed to retrieval |

***REMOVED******REMOVED******REMOVED*** Critical Errors (No Degradation)

| Node Failure | Behavior |
|--------------|----------|
| `classify` | Default to `KNOWLEDGE` type |
| `guard` | Default to `pass` (allow query) |

***REMOVED******REMOVED*** CRM Errors

***REMOVED******REMOVED******REMOVED*** Kommo API Errors

```python
***REMOVED*** telegram_bot/services/kommo_client.py
class KommoError(Exception):
    pass

class KommoAuthError(KommoError):
    """OAuth token expired or invalid."""
    pass

class KommoRateLimitError(KommoError):
    """Rate limit exceeded."""
    pass
```

| Error | User Impact | Recovery |
|-------|-------------|----------|
| `KommoAuthError` | Lead actions fail | Manual retry |
| `KommoRateLimitError` | Temporary failure | Auto-retry after delay |
| `KommoNotFoundError` | Lead not found | Show error to user |
| `KommoValidationError` | Invalid data | Show validation error |

***REMOVED******REMOVED******REMOVED*** Handoff Errors

| Error | Behavior |
|-------|----------|
| `HandoffTimeout` | Auto-reject after 300s |
| `HandoffStateCorrupt` | Reject and log |
| `RedisConnectionError` | Handoff fails, user notified |

***REMOVED******REMOVED*** Ingestion Errors

***REMOVED******REMOVED******REMOVED*** Docling Errors

| Error | Impact | Recovery |
|-------|--------|----------|
| `ParseError` | Document skipped | Check DLQ |
| `ChunkError` | Partial ingestion | Ingest valid chunks |
| `EmbeddingError` | Retry with backoff | 3 retries |

***REMOVED******REMOVED******REMOVED*** Qdrant Write Errors

| Error | Impact | Recovery |
|-------|--------|----------|
| `CollectionNotFound` | Fatal | Run bootstrap |
| `DimensionMismatch` | Fatal | Check embedding config |
| `WriteTimeout` | Retry | Auto-retry 3x |

***REMOVED******REMOVED*** Logging and Tracing

All errors are:
1. Logged with full stack trace
2. Traced in Langfuse (if in pipeline context)
3. Shown to user as friendly message (Telegram only)

```python
***REMOVED*** Error logging format
logger.error(
    "Error in {function}",
    extra={"error": str(e), "traceback": traceback.format_exc()}
)
```

***REMOVED******REMOVED*** Debugging Errors

1. **Telegram bot errors:** Check Langfuse trace for the query
2. **API errors:** Look for `trace_id` in 500 response
3. **Handoff errors:** Check Redis keys `handoff:*`
4. **Ingestion errors:** Check DLQ in PostgreSQL

```bash
***REMOVED*** Check recent errors in Langfuse
make validate-traces-fast

***REMOVED*** Check handoff state
redis-cli GET "handoff:{thread_id}"

***REMOVED*** Check DLQ
uv run python -m src.ingestion.unified.cli status
```
