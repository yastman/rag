---
description: "Known errors and fixes for common development issues"
---

# Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` (requires `REDIS_PASSWORD`) |
| Qdrant timeout | `QDRANT_TIMEOUT=30` |
| Docling 0 chunks | Don't set `tokenizer="word"`, use `None` |
| `Model gpt-4o-mini not found` (404) | `LLM_BASE_URL` must point to LiteLLM, not directly to Cerebras |
| Langfuse traces missing locally | `make run-bot` uses `uv run --env-file .env` to load env vars |
| Cache always MISS | Store guard threshold on RRF scale (~0.005), not cosine [0-1] |
| `qdrant-client .search()` AttributeError | Migrated to `.query_points()` in v1.17 — never use `.search()` |
| ColBERT rerank 16s on CPU | Server-side ColBERT via Qdrant nested prefetch, or `RERANK_PROVIDER=none` |
| Kommo `kommo_client = None` | `KOMMO_CLIENT_ID` (not `KOMMO_INTEGRATION_ID`), `KOMMO_CLIENT_SECRET`, `KOMMO_REDIRECT_URI` |
| TTFT drift warnings spam | `TTFT_DRIFT_WARN_MS=500`; raise for reasoning models behind proxy |
