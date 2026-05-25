# Architecture Decision Records

This directory is the canonical entrypoint for architecture decision records. [`../ADRS.md`](../ADRS.md) is kept only as a legacy compatibility pointer and should not duplicate ADR contents.

## Index

- [0001 - ColBERT reranking](0001-colbert-reranking.md)
- [0002 - BGE-M3 embeddings](0002-bge-m3-embeddings.md)
- [0003 - LangGraph voice/text split](0003-langgraph-voice-text-split.md)
- [0004 - RedisVL semantic cache](0004-redisvl-semantic-cache.md)
- [0005 - Hybrid search with RRF](0005-hybrid-search-rrf.md)
- [0006 - Kommo CRM](0006-kommo-crm.md)
- [0007 - Custom HyDE justified](0007-hyde-custom-justified.md)
- [0008 - `instructor.create_partial` deferred](0008-instructor-create-partial-deferred.md)
- [0009 - LangGraph `Send` fan-out scoping](0009-langgraph-send-fanout-scoping.md)
- [0010 - Voice path `create_agent` migration plan](0010-voice-path-create-agent-migration-plan.md)
- [0011 - Docker Compose as primary runtime](0011-docker-compose-primary-runtime.md)
- [0012 - LangGraph state machine orchestration](0012-langgraph-orchestration.md)
- [0013 - CocoIndex + Docling ingestion pipeline](0013-cocoindex-docling-ingestion.md)
- [0014 - Properties CSV as source of truth (no admin panel)](0014-properties-csv-as-source-of-truth.md)
- [0015 - SDK-native baseline (aiogram, LangGraph, Langfuse, Qdrant)](0015-sdk-native-baseline.md)

## When To Use

Start here when changing retrieval architecture, embeddings, reranking, semantic cache behavior, CRM integration, or voice/Text LangGraph boundaries. Verify every ADR against current code before treating it as active implementation truth.

## Adding ADRs

Create a new `NNNN-short-title.md` file in this directory and add it to the index above. Keep decisions concise: context, decision, consequences, and current implementation notes when implementation details matter.
