# Architecture Decision Records (Legacy Summary)

This page is a legacy summary. The canonical ADR entrypoint is [`adr/README.md`](adr/README.md), and individual ADRs live in [`adr/`](adr/).

Use the canonical ADR directory when changing retrieval architecture, embeddings, reranking, semantic cache behavior, CRM integration, or voice/text LangGraph boundaries. Verify every ADR against current code before treating it as active implementation truth.

## Current ADR Index

- [`adr/0001-colbert-reranking.md`](adr/0001-colbert-reranking.md) - ColBERT reranking
- [`adr/0002-bge-m3-embeddings.md`](adr/0002-bge-m3-embeddings.md) - BGE-M3 embeddings
- [`adr/0003-langgraph-voice-text-split.md`](adr/0003-langgraph-voice-text-split.md) - LangGraph voice/text split
- [`adr/0004-redisvl-semantic-cache.md`](adr/0004-redisvl-semantic-cache.md) - RedisVL semantic cache
- [`adr/0005-hybrid-search-rrf.md`](adr/0005-hybrid-search-rrf.md) - Hybrid search with RRF
- [`adr/0006-kommo-crm.md`](adr/0006-kommo-crm.md) - Kommo CRM

## Adding ADRs

Create new ADRs under [`adr/`](adr/) and update [`adr/README.md`](adr/README.md). Keep this file as a compatibility pointer, not a second source of truth.
