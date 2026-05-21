# ADR-0013: CocoIndex + Docling for Unified Ingestion Pipeline

**Status:** Accepted

**Date:** 2025-05-21

## Context

The platform needed deterministic document ingestion: watch a file source, parse documents, chunk, embed, upsert/delete vectors in Qdrant, and track processing state with retry and dead-letter queue (DLQ) support. We evaluated several approaches:

1. **CocoIndex + Docling** - CocoIndex for flow orchestration and change detection, Docling for document parsing and chunking
2. **LlamaIndex** - Full-featured indexing framework with document loaders and vector store integrations
3. **Unstructured.io** - Document parsing platform (SaaS or self-hosted)
4. **Custom file-watcher scripts** - Hand-rolled inotify/polling with manual state management
5. **Haystack** - Pipeline framework for document processing and retrieval

## Decision

We chose **CocoIndex** for flow orchestration and change detection combined with **Docling** for document parsing and chunking.

### Why CocoIndex + Docling

1. **Stable file identity** - Content-hash-based identity ensures consistent tracking across renames and moves
2. **Automatic change detection** - Only re-processes modified files, reducing compute and API costs
3. **PostgreSQL state tracking** - Durable processing state with DLQ for failed documents
4. **Clean separation of concerns** - CocoIndex handles flow orchestration; Docling handles parsing
5. **Retry and DLQ support** - Failed documents are tracked and can be reprocessed without re-running the full pipeline

### Why Not Others

| Approach | Reason Rejected |
|----------|----------------|
| LlamaIndex | Heavier framework; less control over file identity and delete propagation |
| Unstructured.io | SaaS dependency or heavy self-hosted requirements; less control over chunking strategy |
| Custom file-watcher scripts | No state management; fragile under restarts and partial failures |
| Haystack | Pipeline framework but weaker at incremental updates and change detection |

## Consequences

### Positive
- Stable file identity via content-hash enables reliable upsert/delete
- Automatic change detection: only modified files are re-processed
- PostgreSQL state tracking with DLQ for failed documents
- Clean separation of concerns (CocoIndex = flow, Docling = parsing)
- CLI interface for operations: preflight, bootstrap, run, status, reprocess

### Negative
- CocoIndex is newer with a smaller community and less documentation
- Docling requires GPU/CPU model warmup time on first parse
- Custom Qdrant target connector needed (not available off-the-shelf)

## Implementation

- `src/ingestion/unified/` - Main ingestion directory
- CLI entry: `src.ingestion.unified.cli` with commands: `preflight`, `bootstrap`, `run`, `status`, `reprocess`
- CocoIndex `LocalFile` source watches `GDRIVE_SYNC_DIR` for document changes
- Docling handles document parsing and chunking with configurable strategies
- BGE-M3 generates dense and sparse embeddings for each chunk
- Custom `QdrantHybridTarget` connector handles vector upsert and delete operations
- PostgreSQL tracks processing state and maintains the dead-letter queue

## References

- [docs/INGESTION.md](../INGESTION.md) - Ingestion pipeline documentation
- [docs/PIPELINE_OVERVIEW.md](../PIPELINE_OVERVIEW.md) - Pipeline overview (section 3: ingestion)
- [src/ingestion/unified/](../../src/ingestion/unified/) - Ingestion implementation directory
