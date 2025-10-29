# Content-Based Deduplication Guide

**Date**: 2025-10-22
**Version**: v1.1 (with deduplication)

---

## What Changed?

### OLD approach (sequential IDs):
```python
# Each run created new points with new IDs
point_id = 1, 2, 3, 4...  # On second run: 133, 134, 135...
```

**Problem**: Duplicates accumulate on repeated processing

### NEW approach (content-based hash IDs):
```python
# ID generated from SHA256 hash of content
point_id = "a3f5e8c9..."  # Always the same for one chunk
```

**Solution**: Qdrant `upsert` automatically updates existing point

---

## How Does Deduplication Work?

### 1. Stable ID Generation
```python
def generate_chunk_id(chunk_text: str, source: str, chunk_index: int) -> str:
    """Generate stable UUID from content hash."""
    content = f"{source}::{chunk_text}"
    hash_obj = hashlib.sha256(content.encode('utf-8'))
    return hash_obj.hexdigest()[:32]  # First 32 hex chars
```

**What's included in hash:**
- `source`: Full path to PDF file
- `chunk_text`: Chunk text
- Result: Unique 32-character hex ID

### 2. Qdrant Upsert Behavior
```python
# If ID exists → UPDATE existing point
# If ID doesn't exist → CREATE new point
qdrant_upsert(collection, chunk_id, vectors, payload)
```

---

## Usage Examples

### Scenario 1: First Run
```bash
./process-pdf.sh document.pdf
```

**Result**:
- Chunk 1: hash `abc123...` → CREATE new point
- Chunk 2: hash `def456...` → CREATE new point
- Chunk 3: hash `789ghi...` → CREATE new point
- **Total points: 3**

### Scenario 2: Repeated Run (same PDF)
```bash
./process-pdf.sh document.pdf  # Again!
```

**Result**:
- Chunk 1: hash `abc123...` → UPDATE existing (content unchanged)
- Chunk 2: hash `def456...` → UPDATE existing (content unchanged)
- Chunk 3: hash `789ghi...` → UPDATE existing (content unchanged)
- **Total points: 3** (no duplicates!)

### Scenario 3: Updated PDF
```bash
# document.pdf changed (Chunk 2 updated, Chunk 4 added)
./process-pdf.sh document.pdf
```

**Result**:
- Chunk 1: hash `abc123...` → UPDATE (unchanged)
- Chunk 2: hash `NEW_HASH` → CREATE (text changed!)
- Chunk 3: hash `789ghi...` → UPDATE (unchanged)
- Chunk 4: hash `jkl012...` → CREATE (new chunk)
- **Total points: 5** (old Chunk 2 + new Chunk 2 + others)

**Note**: Old Chunk 2 remains in database (can be deleted manually if needed)

### Scenario 4: Cross-Document Deduplication
```bash
./process-pdf.sh doc1.pdf
./process-pdf.sh doc2.pdf  # Contains same chunks
```

**Result**:
- If chunks are identical → they use different IDs (because of `source` in hash)
- If you want **global deduplication** → remove `source` from hash

---

## Configuring Behavior

### Option 1: Per-Document Deduplication (current)
```python
# In generate_chunk_id():
content = f"{source}::{chunk_text}"
```

**Effect**: Identical chunks from different PDFs have **different IDs**

**Use case**: Each document is independent (Civil Code, Criminal Code)

### Option 2: Global Deduplication
```python
# Change in generate_chunk_id():
content = chunk_text  # Remove source!
```

**Effect**: Identical chunks from any PDFs have **the same ID**

**Use case**: You want to store unique chunks across all documents

### Option 3: Versioned Deduplication
```python
# Add timestamp to hash:
import datetime
content = f"{source}::{chunk_text}::{datetime.date.today()}"
```

**Effect**: New IDs created each day

**Use case**: Tracking historical changes

---

## What Happens During UPDATE?

When Qdrant sees an existing ID:

```python
# OLD point (before update):
{
  "id": "abc123...",
  "vector": [0.1, 0.2, ...],
  "payload": {
    "text": "Article 13...",
    "contextual_prefix": "Old context",
    ...
  }
}

# NEW point (after upsert):
{
  "id": "abc123...",  # Same ID
  "vector": [0.1, 0.2, ...],  # Overwritten!
  "payload": {
    "text": "Article 13...",
    "contextual_prefix": "New context from Z.AI",  # Updated!
    ...
  }
}
```

**Everything is replaced**: vector, payload, everything!

---

## Payload Now Includes Hash ID

```json
{
  "text": "Chunk text...",
  "chunk_id": "a3f5e8c9...",  // NEW! For reference/debugging
  "contextual_prefix": "Context...",
  "document": "Civil Code",
  "source": "/path/to/file.pdf",
  "chunk_index": 42
}
```

**Why?** You can find point by hash in payload:
```python
# Search by hash
from qdrant_client.models import Filter, FieldCondition, MatchValue

client.scroll(
    collection_name="my_collection",
    scroll_filter=Filter(
        must=[
            FieldCondition(
                key="chunk_id",
                match=MatchValue(value="a3f5e8c9...")
            )
        ]
    )
)
```

---

## Important Notes

### What's Protected:
- **Exact duplicates** - automatically updated
- **Repeated processing** - safe, creates 0 new points
- **Concurrency** - SHA256 hash is deterministic, no race conditions

### What's NOT Protected:
- **Minor text changes** - even a space will change hash → new point
- **Encoding differences** - UTF-8 vs CP1251 → different hashes
- **Normalized vs raw text** - "Article  13" vs "Article 13" → different hashes

### Best Practices:
1. **Normalize text** before hashing (lowercase, trim spaces, etc.)
2. **Use same PDF source** - different paths → different hashes
3. **Clean before re-processing** - if you want fresh start:
   ```bash
   # Delete collection before re-processing
   curl -X DELETE "http://localhost:6333/collections/my_collection"
   ```

---

## Debugging

### Check hash for chunk:
```python
import hashlib

chunk_text = "Your chunk text..."
source = "/path/to/file.pdf"
content = f"{source}::{chunk_text}"
hash_id = hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]
print(f"Chunk ID: {hash_id}")
```

### Find duplicate chunks:
```python
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")

# Get all points
points = client.scroll(
    collection_name="my_collection",
    limit=10000,
    with_payload=True
)[0]

# Group by chunk_id
from collections import defaultdict
duplicates = defaultdict(list)
for point in points:
    chunk_id = point.payload.get('chunk_id')
    duplicates[chunk_id].append(point.id)

# Find duplicates
for chunk_id, point_ids in duplicates.items():
    if len(point_ids) > 1:
        print(f"Duplicate: {chunk_id} appears {len(point_ids)} times")
```

---

## Relation to Qdrant Best Practices

From [Qdrant docs](https://qdrant.tech/documentation/):

> **Point IDs can be any unique identifier**: integers, UUIDs, or strings. Using content-based IDs (like SHA256 hash) enables automatic deduplication via upsert operation.

**Advantages of content-based IDs**:
1. Idempotent writes - can run pipeline multiple times
2. No external ID tracking - no need for separate ID mapping database
3. Automatic dedup - Qdrant does everything automatically
4. Fast lookups - hash ID = direct point access (O(1))

---

## Further Reading

- [Qdrant Upsert Documentation](https://qdrant.tech/documentation/concepts/points/#upload-points)
- [SHA256 Hash Collisions](https://en.wikipedia.org/wiki/SHA-2) - probability ~0 for our data
- [Content Addressing](https://en.wikipedia.org/wiki/Content-addressable_storage) - concept of hash-based IDs

---

**Version**: 1.1
**File**: `/srv/app/ingestion_contextual_kg_fast.py`
**Function**: `generate_chunk_id()` (lines 110-134)

**Questions?** Check examples above or run `./process-pdf.sh --help`
