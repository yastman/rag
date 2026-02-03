---
paths: "src/ingestion/**"
---

***REMOVED*** Document Ingestion

Parsing, chunking, and indexing documents into Qdrant.

***REMOVED******REMOVED*** Purpose

Convert PDF/DOCX/CSV/Google Drive documents into searchable vector embeddings in Qdrant.

***REMOVED******REMOVED*** Architecture (CocoIndex Pipeline)

```
Google Drive / Local Files
        │
        ▼ (CocoIndex: 60s polling)
┌───────────────────────────────────────────┐
│ IngestionService (src/ingestion/service.py) │
│ State: Postgres (cocoindex database)        │
└───────────────────────────────────────────┘
        │
        ▼
docling-serve (PDF, DOCX, etc.) → TokenChunker (512 tokens)
        │
        ▼
Voyage API (batched, 100 chunks/request)
        │
        ▼ Replace semantics
Qdrant (DELETE by file_id → UPSERT new chunks)
```

***REMOVED******REMOVED*** Quick Commands

```bash
make ingest-setup         ***REMOVED*** Create Postgres schema + Qdrant indexes
make ingest-run           ***REMOVED*** Run ingestion once
make ingest-continuous    ***REMOVED*** Run with polling
make ingest-status        ***REMOVED*** Show indexed files
make ingest-gdrive-run    ***REMOVED*** Run GDrive ingestion (~/drive-sync)
```

***REMOVED******REMOVED*** Key Files (2026)

| File | Description |
|------|-------------|
| `src/ingestion/service.py` | IngestionService class |
| `src/ingestion/cocoindex_flow.py` | CocoIndex flow definition |
| `src/ingestion/docling_client.py` | Docling API client (httpx async) |
| `src/ingestion/gdrive_flow.py` | Google Drive ingestion flow |
| `src/ingestion/gdrive_indexer.py` | GDrive → Qdrant indexer |
| `telegram_bot/services/ingestion_cocoindex.py` | CLI wrapper |

***REMOVED******REMOVED*** Legacy Architecture

```
Document → Parser (PyMuPDF/Docling) → Chunker (semantic/fixed)
        → VoyageIndexer (dense + BM42 sparse) → Qdrant upsert
```

***REMOVED******REMOVED*** Key Files

| File | Line | Description |
|------|------|-------------|
| `src/ingestion/document_parser.py` | 45 | ParserCache |
| `src/ingestion/document_parser.py` | 80+ | UniversalDocumentParser |
| `src/ingestion/chunker.py` | 34 | DocumentChunker |
| `src/ingestion/chunker.py` | 230 | chunk_csv_by_rows() |
| `src/ingestion/voyage_indexer.py` | 47 | VoyageIndexer |

***REMOVED******REMOVED*** Parser Selection

| Format | Parser | Speed |
|--------|--------|-------|
| PDF | PyMuPDF | 377x faster than Docling |
| DOCX | Docling | Universal converter |
| CSV | chunk_csv_by_rows() | Row-per-chunk |

***REMOVED******REMOVED*** Chunking Strategies

| Strategy | Use Case | Description |
|----------|----------|-------------|
| SEMANTIC | Legal docs | Respects sections, chapters |
| FIXED_SIZE | General | 1024 chars with 256 overlap |
| SLIDING_WINDOW | Dense coverage | Overlapping windows |

***REMOVED******REMOVED*** Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 1024 | Target chars per chunk |
| `overlap` | 256 | Overlap between chunks |
| `VOYAGE_BATCH_SIZE` | 128 | Texts per API request |

***REMOVED******REMOVED*** Common Patterns

***REMOVED******REMOVED******REMOVED*** Parse document

```python
from src.ingestion.document_parser import UniversalDocumentParser

parser = UniversalDocumentParser(use_cache=True)
doc = parser.parse_file("document.pdf")
print(doc.content)
```

***REMOVED******REMOVED******REMOVED*** Chunk text

```python
from src.ingestion.chunker import DocumentChunker, ChunkingStrategy

chunker = DocumentChunker(
    chunk_size=1024,
    overlap=256,
    strategy=ChunkingStrategy.SEMANTIC,
)

chunks = chunker.chunk_text(
    text=doc.content,
    document_name="legal_code.pdf",
    article_number="doc_001",
)
```

***REMOVED******REMOVED******REMOVED*** Chunk CSV (row-per-chunk)

```python
from src.ingestion.chunker import chunk_csv_by_rows

chunks = chunk_csv_by_rows(
    csv_path=Path("properties.csv"),
    document_name="bulgaria_properties",
)
***REMOVED*** Each row becomes one chunk with structured metadata
```

***REMOVED******REMOVED******REMOVED*** Index to Qdrant

```python
from src.ingestion.voyage_indexer import VoyageIndexer

indexer = VoyageIndexer(
    qdrant_url="http://localhost:6333",
    voyage_api_key=api_key,
    voyage_model="voyage-4-large",
)

stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="contextual_bulgaria_voyage",
)
print(f"Indexed {stats.indexed_chunks} chunks")
```

***REMOVED******REMOVED*** CSV Metadata Extraction

Automatic field mapping:

| CSV Column | Metadata Field | Type |
|------------|----------------|------|
| Название | title | string |
| Город | city | string |
| Цена (€) | price | int |
| Комнат | rooms | int |
| Площадь (м²) | area | float |
| Этаж | floor | int |
| До моря (м) | distance_to_sea | int |

***REMOVED******REMOVED*** Parser Cache

MD5-based caching to skip re-parsing:

```python
parser = UniversalDocumentParser(use_cache=True)
***REMOVED*** First call: parses and caches
***REMOVED*** Second call: returns from .cache/parser/
```

***REMOVED******REMOVED*** Qdrant Collection Setup

VoyageIndexer creates collection with:
- Dense vectors: 1024-dim, cosine distance
- Sparse vectors: BM42
- Scalar Int8 quantization (4x compression)

***REMOVED******REMOVED*** Dependencies

- Container: `dev-docling` (5001), 4GB RAM
- Voyage API for embeddings
- Qdrant for storage

***REMOVED******REMOVED*** Google Drive Ingestion

```bash
***REMOVED*** Setup rclone (one time)
rclone config  ***REMOVED*** Create "gdrive" remote with OAuth

***REMOVED*** Sync files
rclone sync gdrive:RAG ~/drive-sync

***REMOVED*** Run ingestion
make ingest-gdrive-run
***REMOVED*** or: uv run python -m src.ingestion.gdrive_flow --once --sync-dir ~/drive-sync
```

***REMOVED******REMOVED******REMOVED*** GDrive Flow Architecture

```
~/drive-sync (rclone) → GDriveFlow → DoclingClient → Voyage → Qdrant
                              ↓
                     .manifest.json (tracks processed files)
```

***REMOVED******REMOVED******REMOVED*** GDrive Collections

| Collection | Quantization |
|------------|--------------|
| `gdrive_documents_scalar` | INT8 (default) |
| `gdrive_documents_binary` | Binary (fast) |

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/test_chunker.py -v
pytest tests/unit/test_document_parser.py -v
pytest tests/unit/test_voyage_indexer.py -v
pytest tests/unit/ingestion/test_docling_client.py -v
pytest tests/unit/ingestion/test_gdrive_flow.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| PyMuPDF import error | `pip install pymupdf` (not `fitz`) |
| Docling slow | Use PyMuPDF for PDFs |
| Voyage 429 | Add delays, reduce batch size |
| Docling returns 0 chunks | Don't set `tokenizer="word"`, use `None` (server default) |
| rclone empty token | Run `rclone config reconnect gdrive:` |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new document format

1. Add parser method to `UniversalDocumentParser`
2. Update `parse_file()` extension detection
3. Add tests with sample document

***REMOVED******REMOVED******REMOVED*** Adding new chunking strategy

1. Add to `ChunkingStrategy` enum
2. Implement `_chunk_new_strategy()` method
3. Add case to `chunk_text()`
