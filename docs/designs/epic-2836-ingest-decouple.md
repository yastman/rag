# Epic #2836: Ingest Decouple

**Status:** Architecture Review
**Owner:** Ingestion Team
**Related:** Epic #2846 (layering), #2831–#2835 (implementation slices)

## Problem Statement

The unified ingestion pipeline (`src/ingestion/unified/`) has a tight structural dependency on CocoIndex for incremental change detection. While CocoIndex is an excellent choice for stable ingestion, the coupling makes it difficult to:

1. Swap the change-detection backend (e.g., to filesystem polling, SQL triggers, or alternative incremental systems).
2. Test ingestion logic independently of CocoIndex machinery.
3. Decompose ingestion into independently deployable services (container per pipeline, orchestrator pattern).

## Current CocoIndex Integration Points

### Files with Direct CocoIndex Imports

| File | Integration | Purpose |
|------|-----------|---------|
| `src/ingestion/unified/flow.py` | `import cocoindex` | Flow assembly, schema setup, CLI control |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | `from cocoindex.op import TargetSpec, target_connector` | Connector registration and mutation dispatch |
| `src/ingestion/unified/targets/__init__.py` | Re-exports | Connector discovery |

### Dependency Flow

```
CocoIndex lifecycle
  ├─ build_flow() → create LocalFile source + QdrantHybridTargetConnector
  ├─ run_once() / run_watch() → orchestrates mutation dispatch
  └─ FlowLiveUpdater → watches files, emits mutations
       ↓
QdrantHybridTargetConnector.mutate()
  ├─ Receives file path + metadata
  ├─ Calls FileState → storage
  ├─ Delegates to QdrantHybridWriter
  └─ Updates Postgres state
```

**Observation:** The connector is tightly coupled to:
- `FileState` / `UnifiedStateManager` (storage layer)
- `QdrantHybridWriter` (embedding + write layer)
- `DoclingClient` (parsing layer)

CocoIndex is the *orchestrator*; the storage, embedding, and write layers are *pluggable*.

## Proposed Architecture: StateManager + QdrantHybridWriter Interface

Decouple the workflow orchestrator from CocoIndex via two stable interfaces:

### 1. StateManager Interface

**Purpose:** Abstract file identity and change detection.

```python
class FileChangeManager(Protocol):
    """Detects file changes and provides file identity."""

    async def detect_changes(
        self,
        collection_name: str,
    ) -> list[FileChange]:
        """Emit file paths and metadata (added, modified, deleted)."""
        ...

    async def record_state(
        self,
        file_path: str,
        collection_name: str,
        state: FileState,
    ) -> None:
        """Mark a file as processed, record hash + embedding metadata."""
        ...
```

**Implementations:**
- `CocoIndexChangeManager` (current): wraps CocoIndex LocalFile + flow
- `FilePollingManager` (future): poll filesystem, maintain sqlite state table
- `S3ChangeManager` (future): S3 event bucket + state in DynamoDB

### 2. QdrantHybridWriter Interface (Already Exists, Clarify Boundary)

The writer is already mostly decoupled; clarify the contract:

```python
class DocumentWriter(Protocol):
    """Writes parsed documents to vector store."""

    async def write_file(
        self,
        file_path: str,
        parsed_doc: ParsedDocument,
        collection_name: str,
    ) -> FileState:
        """Parse, embed, upsert to Qdrant. Return state metadata."""
        ...

    async def delete_file(
        self,
        file_path: str,
        collection_name: str,
    ) -> None:
        """Delete all points for a file from Qdrant."""
        ...
```

**Implementation:** `QdrantHybridWriter` remains concrete (no swap needed soon).

### 3. Unified Ingestion Orchestrator (New)

```python
class UnifiedIngestionOrchestrator:
    """High-level ingestion loop, agnostic to change detection backend."""

    def __init__(
        self,
        change_manager: FileChangeManager,
        writer: DocumentWriter,
        state_manager: UnifiedStateManager,
    ):
        self.change_manager = change_manager
        self.writer = writer
        self.state_manager = state_manager

    async def run_once(self, collection_name: str) -> IngestionResult:
        """Detect changes, process files, update state."""
        changes = await self.change_manager.detect_changes(collection_name)

        for change in changes:
            if change.kind == "added" or change.kind == "modified":
                state = await self.writer.write_file(
                    change.file_path, collection_name
                )
                await self.change_manager.record_state(
                    change.file_path, collection_name, state
                )
            elif change.kind == "deleted":
                await self.writer.delete_file(change.file_path, collection_name)

    async def run_watch(self, collection_name: str) -> None:
        """Run ingestion in a loop (implementation detail per change manager)."""
        ...
```

## Implementation Sequence

| Slice | Issue | Goal | Effort |
|-------|-------|------|--------|
| 1 | #2831 | Add unit tests for character-level chunk stability | 2pt |
| 2 | #2832 | Extract orchestrator loop into `UnifiedIngestionOrchestrator` | 5pt |
| 3 | #2833 | Define and implement `FileChangeManager` protocol | 3pt |
| 4 | #2834 | Wrap CocoIndex in `CocoIndexChangeManager`, verify parity | 5pt |
| 5 | #2835 | Cleanup: remove direct CocoIndex imports from flow.py | 2pt |

**Verification:** Each slice has passing tests; integration E2E against fixture corpus.

## Done Criteria

- ✓ `FileChangeManager` protocol documented with at least two implementation stubs
- ✓ `UnifiedIngestionOrchestrator` accepts injected change manager
- ✓ `CocoIndexChangeManager` wraps CocoIndex and passes existing ingestion tests
- ✓ CLI and service entry points use the orchestrator (no CocoIndex imports in public interfaces)
- ✓ New feature: `FilePollingManager` can be swapped in without touching orchestrator
- ✓ All ingestion E2E tests (fixture corpus, Qdrant hybrid write, state tracking) pass

## Layering Benefit

This decoupling also enables #2846 (layering fix) by:
- Moving orchestrator-layer logic out of CocoIndex callbacks
- Making `src/ingestion/unified/` a data-transformation library, not an orchestration sidecar
- Allowing future adapter layers (e.g., Kafka ingest, webhook trigger) to use the same Writer + StateManager pair

## Non-Goals

- Remove CocoIndex from the codebase (it remains the primary change detector for VPS and SaaS)
- Break existing CLI or service interfaces
- Alter Qdrant schema or embedding generation
