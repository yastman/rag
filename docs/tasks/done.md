# Выполненные задачи

> История завершённых задач

---

## v2.8.0 — Resilience & Observability (2025-01-06)

- Graceful degradation для всех сервисов
- Structured JSON logging
- LLM fallback answers
- Health checks

## v2.7.0 — User Experience (2025-01-06)

- Streaming LLM responses (0.1s TTFB)
- Conversation memory
- Cross-encoder reranking (+10-15% accuracy)
- /clear и /stats команды

## v2.6.0 — Critical Fixes (2025-01-06)

- **1.1** Security: Removed exposed API keys
- **1.2** Performance: requests -> httpx.AsyncClient
- **1.3** Dependencies: Complete requirements.txt
- **1.4** Performance: Fixed blocking async calls
- **2.1** BGE-M3 singleton pattern (saves 4-6GB RAM)

## v2.5.0 — Semantic Cache (2025-11-05)

- 4-tier caching architecture
- Redis Vector Search integration
- 70-80% cache hit rate

## v2.4.0 — Universal Indexer (2025-11-05)

- CSV/DOCX/XLSX support
- Demo files organization

## v2.3.0 — DBSF + ColBERT (2025-10-30)

- Variant B search engine
- A/B testing framework

## v2.2.0 — RRF + ColBERT (2025-10-30)

- Variant A search engine (default)
- BM42 sparse vectors

## v2.1.0 — ML Platform (2025-10-30)

- MLflow integration
- Langfuse tracing
- 2-level Redis cache
- PII redaction
- Budget guards

## v2.0.0 — BGE-M3 (2025-10-25)

- Multi-vector embeddings
- Qdrant optimizations
- Int8 quantization

## v1.0.0 — Initial Release (2025-10-15)

- Basic RAG pipeline
- PDF parsing
- Baseline search

---

**Последнее обновление:** 2026-01-21
