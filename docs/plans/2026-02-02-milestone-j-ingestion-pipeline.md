# Milestone J — Document Ingestion Pipeline (Production-Ready)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Автоматический pipeline Google Drive → Qdrant с incremental updates, production-grade reliability

**Architecture:** CocoIndex (state + polling) → docling-serve (parsing) → Voyage (embeddings) → Qdrant (vectors)

**Tech Stack:** CocoIndex, Postgres, docling-serve, Voyage AI, Qdrant, Redis (queue)

---

## Архитектура

```
Google Drive Folder
        │
        ▼ (recent_changes: 60s, refresh: 6h)
┌───────────────────────────────────────────┐
│  CocoIndex Pipeline                        │
│  State: Postgres (dev-postgres/cocoindex)  │
└───────────────────────────────────────────┘
        │
        ▼ Format Router
┌───────────────────────────────────────────┐
│ Google Docs  → Export HTML → Docling      │
│ Google Sheets → Export CSV → Row chunking │
│ PDF/DOCX     → Docling API                │
│ MD/TXT       → Direct read                │
└───────────────────────────────────────────┘
        │
        ▼ docling-serve (dev-docling:5001)
┌───────────────────────────────────────────┐
│ POST /v1/convert/file                      │
│ - pdf_backend: dlparse_v2                  │
│ - table_mode: accurate                     │
│ - ocr_lang: [ru, en, bg]                   │
│ - to_formats: [md]                         │
└───────────────────────────────────────────┘
        │
        ▼ Token-based Chunking (512 tokens)
┌───────────────────────────────────────────┐
│ HybridChunker (Voyage tokenizer)           │
│ - max_tokens: 512                          │
│ - overlap: 50 tokens                       │
│ - merge_peers: true                        │
└───────────────────────────────────────────┘
        │
        ▼ Voyage API (batched, 100 chunks/request)
┌───────────────────────────────────────────┐
│ voyage-3-large embeddings                  │
│ - retry: 3 attempts, exponential backoff   │
│ - rate limit: 300 RPM                      │
└───────────────────────────────────────────┘
        │
        ▼ Qdrant (replace semantics)
┌───────────────────────────────────────────┐
│ 1. DELETE WHERE file_id = X               │
│ 2. UPSERT new chunks                       │
│ Point ID: {file_id}:{chunk_idx}           │
│ Payload index: file_id, folder_id          │
└───────────────────────────────────────────┘
```

---

## Postgres State Schema

```sql
-- Database: cocoindex

CREATE TABLE ingestion_state (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) UNIQUE NOT NULL,
    drive_id VARCHAR(255),
    folder_id VARCHAR(255),
    file_name VARCHAR(500),
    mime_type VARCHAR(100),
    modified_time TIMESTAMPTZ,
    content_hash VARCHAR(64),           -- SHA256 of file content
    parser_version VARCHAR(20),          -- e.g., "docling-2.1"
    chunker_version VARCHAR(20),         -- e.g., "hybrid-1.0"
    embedding_model VARCHAR(50),         -- e.g., "voyage-3-large"
    chunk_count INTEGER,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, indexed, error
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_file_id ON ingestion_state(file_id);
CREATE INDEX idx_folder_id ON ingestion_state(folder_id);
CREATE INDEX idx_status ON ingestion_state(status);
CREATE INDEX idx_modified_time ON ingestion_state(modified_time);

-- Dead letter queue for failed items
CREATE TABLE ingestion_dead_letter (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) NOT NULL,
    error_type VARCHAR(100),
    error_message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Qdrant Payload Schema

```json
{
  "file_id": "gdrive_abc123",
  "folder_id": "folder_xyz",
  "file_name": "ВНЖ для фрилансеров.md",
  "mime_type": "text/markdown",
  "chunk_idx": 0,
  "chunk_count": 12,
  "content_hash": "sha256:abc...",
  "text": "Chunk text content...",
  "source_url": "https://drive.google.com/file/d/abc123",
  "modified_time": "2026-02-02T14:30:00Z",
  "indexed_at": "2026-02-02T14:35:00Z",
  "parser_version": "docling-2.1",
  "embedding_model": "voyage-3-large"
}
```

**Payload Indexes (создать в Qdrant):**
```python
client.create_payload_index(
    collection_name="documents",
    field_name="file_id",
    field_schema="keyword"
)
client.create_payload_index(
    collection_name="documents",
    field_name="folder_id",
    field_schema="keyword"
)
```

---

## Задачи

### Task 1: Postgres Setup

**Files:**
- Modify: `docker-compose.dev.yml`
- Create: `docker/postgres/init/02-cocoindex.sql`

**Step 1: Create init SQL**

```sql
-- docker/postgres/init/02-cocoindex.sql
CREATE DATABASE cocoindex;

\c cocoindex;

CREATE TABLE ingestion_state (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) UNIQUE NOT NULL,
    drive_id VARCHAR(255),
    folder_id VARCHAR(255),
    file_name VARCHAR(500),
    mime_type VARCHAR(100),
    modified_time TIMESTAMPTZ,
    content_hash VARCHAR(64),
    parser_version VARCHAR(20),
    chunker_version VARCHAR(20),
    embedding_model VARCHAR(50),
    chunk_count INTEGER,
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_file_id ON ingestion_state(file_id);
CREATE INDEX idx_folder_id ON ingestion_state(folder_id);
CREATE INDEX idx_status ON ingestion_state(status);

CREATE TABLE ingestion_dead_letter (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) NOT NULL,
    error_type VARCHAR(100),
    error_message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Step 2: Verify init script runs**

```bash
docker compose down postgres && docker volume rm rag-fresh_postgres_data
docker compose up -d postgres
docker exec dev-postgres psql -U postgres -c "\l" | grep cocoindex
```

Expected: `cocoindex` database listed

**Step 3: Commit**

```bash
git add docker/postgres/init/02-cocoindex.sql
git commit -m "feat(ingestion): add cocoindex database schema"
```

---

### Task 2: Add CocoIndex Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

**Step 1: Add dependencies**

```toml
# pyproject.toml [project.dependencies]
"cocoindex>=0.1.0",
```

**Step 2: Add env vars**

```bash
# .env.example
COCOINDEX_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cocoindex
GOOGLE_DRIVE_FOLDER_ID=your_folder_id
GOOGLE_SERVICE_ACCOUNT_KEY_PATH=./credentials/gdrive-service-account.json
```

**Step 3: Install and verify**

```bash
uv sync
uv run python -c "import cocoindex; print('OK')"
```

**Step 4: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "feat(ingestion): add cocoindex dependency"
```

---

### Task 3: Create Docling Client

**Files:**
- Create: `src/ingestion/docling_client.py`
- Create: `tests/unit/test_docling_client.py`

**Step 1: Write failing test**

```python
# tests/unit/test_docling_client.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_convert_file_returns_markdown():
    from src.ingestion.docling_client import DoclingClient

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"document": {"md_content": "# Test"}}
        )

        client = DoclingClient("http://localhost:5001")
        result = await client.convert_file(b"fake pdf", "test.pdf")

        assert result == "# Test"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_docling_client.py -v
```

Expected: FAIL (module not found)

**Step 3: Implement DoclingClient**

```python
# src/ingestion/docling_client.py
import httpx
from typing import Optional
import hashlib

class DoclingClient:
    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        timeout: float = 120.0,
        ocr_langs: list[str] = ["ru", "en", "bg"],
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.ocr_langs = ocr_langs
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: dict[str, str] = {}  # content_hash -> markdown

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    def _content_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def convert_file(
        self,
        content: bytes,
        filename: str,
        use_cache: bool = True,
    ) -> str:
        """Convert file to markdown via docling-serve."""
        content_hash = self._content_hash(content)

        # Check cache
        if use_cache and content_hash in self._cache:
            return self._cache[content_hash]

        client = await self._get_client()

        # Determine mime type
        mime_type = self._get_mime_type(filename)

        response = await client.post(
            f"{self.base_url}/v1/convert/file",
            files={"files": (filename, content, mime_type)},
            data={
                "to_formats": ["md"],
                "pdf_backend": "dlparse_v2",
                "table_mode": "accurate",
                "do_ocr": True,
                "ocr_lang": self.ocr_langs,
            },
        )
        response.raise_for_status()

        result = response.json()
        markdown = result.get("document", {}).get("md_content", "")

        # Cache result
        if use_cache:
            self._cache[content_hash] = markdown

        return markdown

    def _get_mime_type(self, filename: str) -> str:
        ext = filename.lower().split(".")[-1]
        mime_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "html": "text/html",
            "md": "text/markdown",
            "txt": "text/plain",
        }
        return mime_map.get(ext, "application/octet-stream")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_docling_client.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/docling_client.py tests/unit/test_docling_client.py
git commit -m "feat(ingestion): add DoclingClient with caching"
```

---

### Task 4: Create Chunker Service

**Files:**
- Create: `src/ingestion/chunker.py`
- Create: `tests/unit/test_chunker.py`

**Step 1: Write failing test**

```python
# tests/unit/test_chunker.py
import pytest

def test_chunk_text_respects_max_tokens():
    from src.ingestion.chunker import TokenChunker

    chunker = TokenChunker(max_tokens=100, overlap_tokens=20)
    text = "word " * 500  # 500 words
    chunks = chunker.chunk(text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunker.count_tokens(chunk) <= 100
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_chunker.py::test_chunk_text_respects_max_tokens -v
```

**Step 3: Implement TokenChunker**

```python
# src/ingestion/chunker.py
from transformers import AutoTokenizer
from typing import Optional

class TokenChunker:
    """Token-based chunker optimized for Voyage embeddings."""

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 50,
        tokenizer_name: str = "bert-base-uncased",
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self._tokenizer: Optional[AutoTokenizer] = None
        self._tokenizer_name = tokenizer_name

    @property
    def tokenizer(self) -> AutoTokenizer:
        if self._tokenizer is None:
            self._tokenizer = AutoTokenizer.from_pretrained(self._tokenizer_name)
        return self._tokenizer

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def chunk(self, text: str) -> list[str]:
        """Split text into chunks respecting token limits."""
        if not text.strip():
            return []

        tokens = self.tokenizer.encode(text, add_special_tokens=False)

        if len(tokens) <= self.max_tokens:
            return [text]

        chunks = []
        start = 0

        while start < len(tokens):
            end = min(start + self.max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens, skip_special_tokens=True)
            chunks.append(chunk_text.strip())

            # Move start with overlap
            start = end - self.overlap_tokens
            if start >= len(tokens) - self.overlap_tokens:
                break

        return chunks
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_chunker.py -v
```

**Step 5: Commit**

```bash
git add src/ingestion/chunker.py tests/unit/test_chunker.py
git commit -m "feat(ingestion): add TokenChunker for Voyage-optimized chunking"
```

---

### Task 5: Create Ingestion Service

**Files:**
- Create: `src/ingestion/service.py`
- Create: `tests/unit/test_ingestion_service.py`

**Step 1: Write failing test**

```python
# tests/unit/test_ingestion_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_ingest_file_creates_chunks_in_qdrant():
    from src.ingestion.service import IngestionService

    mock_docling = AsyncMock()
    mock_docling.convert_file.return_value = "# Title\n\nContent here"

    mock_voyage = AsyncMock()
    mock_voyage.embed.return_value = [[0.1] * 1024]

    mock_qdrant = MagicMock()

    service = IngestionService(
        docling_client=mock_docling,
        voyage_client=mock_voyage,
        qdrant_client=mock_qdrant,
        collection_name="test",
    )

    result = await service.ingest_file(
        file_id="file123",
        content=b"fake content",
        filename="test.pdf",
        folder_id="folder456",
    )

    assert result["status"] == "indexed"
    assert result["chunk_count"] >= 1
    mock_qdrant.delete.assert_called_once()  # Replace semantics
    mock_qdrant.upsert.assert_called_once()
```

**Step 2: Implement IngestionService**

```python
# src/ingestion/service.py
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from src.ingestion.docling_client import DoclingClient
from src.ingestion.chunker import TokenChunker

PARSER_VERSION = "docling-2.1"
CHUNKER_VERSION = "token-1.0"
EMBEDDING_MODEL = "voyage-3-large"

@dataclass
class IngestionResult:
    status: str
    file_id: str
    chunk_count: int
    content_hash: str
    error: Optional[str] = None

class IngestionService:
    def __init__(
        self,
        docling_client: DoclingClient,
        voyage_client: Any,  # VoyageService
        qdrant_client: QdrantClient,
        collection_name: str,
        chunker: Optional[TokenChunker] = None,
        batch_size: int = 100,
    ):
        self.docling = docling_client
        self.voyage = voyage_client
        self.qdrant = qdrant_client
        self.collection_name = collection_name
        self.chunker = chunker or TokenChunker()
        self.batch_size = batch_size

    async def ingest_file(
        self,
        file_id: str,
        content: bytes,
        filename: str,
        folder_id: str,
        source_url: Optional[str] = None,
        modified_time: Optional[datetime] = None,
    ) -> dict:
        """Ingest a file with replace semantics."""
        content_hash = hashlib.sha256(content).hexdigest()
        now = datetime.now(timezone.utc)

        try:
            # 1. Parse with Docling
            markdown = await self.docling.convert_file(content, filename)

            # 2. Chunk
            chunks = self.chunker.chunk(markdown)
            if not chunks:
                return {
                    "status": "skipped",
                    "file_id": file_id,
                    "chunk_count": 0,
                    "content_hash": content_hash,
                    "error": "No content after parsing",
                }

            # 3. Embed (batched)
            embeddings = []
            for i in range(0, len(chunks), self.batch_size):
                batch = chunks[i:i + self.batch_size]
                batch_embeddings = await self.voyage.embed(batch)
                embeddings.extend(batch_embeddings)

            # 4. Delete old chunks (replace semantics)
            self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="file_id",
                            match=MatchValue(value=file_id),
                        )
                    ]
                ),
            )

            # 5. Upsert new chunks
            points = []
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                point_id = f"{file_id}:{idx}"
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "file_id": file_id,
                            "folder_id": folder_id,
                            "file_name": filename,
                            "chunk_idx": idx,
                            "chunk_count": len(chunks),
                            "content_hash": content_hash,
                            "text": chunk,
                            "source_url": source_url or "",
                            "modified_time": modified_time.isoformat() if modified_time else "",
                            "indexed_at": now.isoformat(),
                            "parser_version": PARSER_VERSION,
                            "embedding_model": EMBEDDING_MODEL,
                        },
                    )
                )

            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=points,
            )

            return {
                "status": "indexed",
                "file_id": file_id,
                "chunk_count": len(chunks),
                "content_hash": content_hash,
            }

        except Exception as e:
            return {
                "status": "error",
                "file_id": file_id,
                "chunk_count": 0,
                "content_hash": content_hash,
                "error": str(e),
            }

    async def delete_file(self, file_id: str) -> bool:
        """Delete all chunks for a file."""
        self.qdrant.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="file_id",
                        match=MatchValue(value=file_id),
                    )
                ]
            ),
        )
        return True
```

**Step 3: Run tests**

```bash
uv run pytest tests/unit/test_ingestion_service.py -v
```

**Step 4: Commit**

```bash
git add src/ingestion/service.py tests/unit/test_ingestion_service.py
git commit -m "feat(ingestion): add IngestionService with replace semantics"
```

---

### Task 6: Create CocoIndex Flow

**Files:**
- Create: `src/ingestion/cocoindex_flow.py`
- Create: `tests/unit/test_cocoindex_flow.py`

**Step 1: Implement CocoIndex flow**

```python
# src/ingestion/cocoindex_flow.py
import os
from typing import Optional
import cocoindex
from cocoindex.sources import GoogleDrive
from cocoindex.storages import Postgres

from src.ingestion.service import IngestionService
from src.ingestion.docling_client import DoclingClient
from src.ingestion.chunker import TokenChunker
from telegram_bot.services.voyage import VoyageService
from qdrant_client import QdrantClient

class IngestionFlow:
    """CocoIndex-based ingestion flow for Google Drive → Qdrant."""

    def __init__(
        self,
        folder_id: str,
        collection_name: str = "documents",
        recent_changes_interval: int = 60,  # seconds
        refresh_interval: int = 21600,  # 6 hours
        database_url: Optional[str] = None,
        docling_url: str = "http://localhost:5001",
        qdrant_url: str = "http://localhost:6333",
    ):
        self.folder_id = folder_id
        self.collection_name = collection_name
        self.recent_changes_interval = recent_changes_interval
        self.refresh_interval = refresh_interval
        self.database_url = database_url or os.getenv("COCOINDEX_DATABASE_URL")
        self.docling_url = docling_url
        self.qdrant_url = qdrant_url

        # Initialize clients
        self.docling = DoclingClient(docling_url)
        self.voyage = VoyageService()
        self.qdrant = QdrantClient(url=qdrant_url)
        self.chunker = TokenChunker()

        self.ingestion_service = IngestionService(
            docling_client=self.docling,
            voyage_client=self.voyage,
            qdrant_client=self.qdrant,
            collection_name=collection_name,
            chunker=self.chunker,
        )

    def create_flow(self) -> cocoindex.Flow:
        """Create CocoIndex flow definition."""

        @cocoindex.flow
        def ingestion_flow():
            # Source: Google Drive
            source = GoogleDrive(
                folder_ids=[self.folder_id],
                service_account_key_path=os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_PATH"),
                recent_changes_poll_interval=self.recent_changes_interval,
                refresh_interval=self.refresh_interval,
            )

            # State storage
            storage = Postgres(connection_url=self.database_url)

            # Process each file
            for file in source.files():
                # Export Google Docs/Sheets if needed
                content = self._export_file(file)

                # Ingest
                result = self.ingestion_service.ingest_file(
                    file_id=file.id,
                    content=content,
                    filename=file.name,
                    folder_id=self.folder_id,
                    source_url=file.web_view_link,
                    modified_time=file.modified_time,
                )

                # Update state
                storage.update_state(file.id, result)

            # Handle deletions
            for deleted_id in source.deleted_files():
                self.ingestion_service.delete_file(deleted_id)
                storage.delete_state(deleted_id)

        return ingestion_flow

    def _export_file(self, file) -> bytes:
        """Export Google Docs/Sheets to downloadable format."""
        mime_type = file.mime_type

        if mime_type == "application/vnd.google-apps.document":
            # Export Google Doc as HTML
            return file.export("text/html")
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            # Export Google Sheet as CSV
            return file.export("text/csv")
        else:
            # Regular file: download
            return file.download()

    async def run_once(self):
        """Run ingestion once (for testing/manual trigger)."""
        flow = self.create_flow()
        await flow.run()

    async def run_continuous(self):
        """Run ingestion continuously."""
        flow = self.create_flow()
        await flow.run_continuous()
```

**Step 2: Add tests**

```python
# tests/unit/test_cocoindex_flow.py
import pytest
from unittest.mock import patch, MagicMock

def test_flow_creates_with_correct_intervals():
    with patch.dict("os.environ", {
        "COCOINDEX_DATABASE_URL": "postgresql://test",
        "GOOGLE_SERVICE_ACCOUNT_KEY_PATH": "/fake/path.json",
    }):
        from src.ingestion.cocoindex_flow import IngestionFlow

        flow = IngestionFlow(
            folder_id="test_folder",
            recent_changes_interval=30,
            refresh_interval=3600,
        )

        assert flow.recent_changes_interval == 30
        assert flow.refresh_interval == 3600
```

**Step 3: Commit**

```bash
git add src/ingestion/cocoindex_flow.py tests/unit/test_cocoindex_flow.py
git commit -m "feat(ingestion): add CocoIndex flow for Google Drive sync"
```

---

### Task 7: Create Qdrant Payload Indexes

**Files:**
- Create: `scripts/setup_ingestion_collection.py`

**Step 1: Create setup script**

```python
# scripts/setup_ingestion_collection.py
"""Setup Qdrant collection and payload indexes for ingestion."""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PayloadSchemaType,
)

COLLECTION_NAME = "documents"
VECTOR_SIZE = 1024  # Voyage-3-large

def setup_collection(client: QdrantClient):
    """Create collection with proper indexes."""

    # Create collection if not exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        print(f"Created collection: {COLLECTION_NAME}")

    # Create payload indexes for fast filtering/deletion
    indexes = [
        ("file_id", PayloadSchemaType.KEYWORD),
        ("folder_id", PayloadSchemaType.KEYWORD),
        ("mime_type", PayloadSchemaType.KEYWORD),
    ]

    for field_name, field_type in indexes:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=field_type,
            )
            print(f"Created index: {field_name}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Index exists: {field_name}")
            else:
                raise

if __name__ == "__main__":
    client = QdrantClient(url="http://localhost:6333")
    setup_collection(client)
    print("Done!")
```

**Step 2: Run script**

```bash
uv run python scripts/setup_ingestion_collection.py
```

**Step 3: Commit**

```bash
git add scripts/setup_ingestion_collection.py
git commit -m "feat(ingestion): add Qdrant collection setup with payload indexes"
```

---

### Task 8: Add Makefile Targets

**Files:**
- Modify: `Makefile`

**Step 1: Add ingestion targets**

```makefile
# Ingestion Pipeline
.PHONY: ingest-setup ingest-run ingest-status ingest-test

ingest-setup: ## Setup ingestion (DB + Qdrant indexes)
	docker exec dev-postgres psql -U postgres -f /docker-entrypoint-initdb.d/02-cocoindex.sql || true
	uv run python scripts/setup_ingestion_collection.py

ingest-run: ## Run ingestion once
	uv run python -c "import asyncio; from src.ingestion.cocoindex_flow import IngestionFlow; asyncio.run(IngestionFlow('$(FOLDER_ID)').run_once())"

ingest-continuous: ## Run continuous ingestion
	uv run python -c "import asyncio; from src.ingestion.cocoindex_flow import IngestionFlow; asyncio.run(IngestionFlow('$(FOLDER_ID)').run_continuous())"

ingest-status: ## Show ingestion status
	docker exec dev-postgres psql -U postgres -d cocoindex -c "SELECT file_id, file_name, status, chunk_count, indexed_at FROM ingestion_state ORDER BY indexed_at DESC LIMIT 20;"

ingest-test: ## Test ingestion with local files
	uv run pytest tests/unit/test_ingestion*.py tests/unit/test_docling*.py tests/unit/test_chunker.py -v
```

**Step 2: Commit**

```bash
git add Makefile
git commit -m "feat(ingestion): add Makefile targets for ingestion pipeline"
```

---

### Task 9: Add Integration Test

**Files:**
- Create: `tests/integration/test_ingestion_e2e.py`

**Step 1: Create E2E test**

```python
# tests/integration/test_ingestion_e2e.py
"""E2E test for ingestion pipeline (requires Docker services)."""
import pytest
import os

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests disabled"
)

@pytest.mark.asyncio
async def test_ingest_local_markdown_file():
    """Test ingesting a local markdown file."""
    from src.ingestion.service import IngestionService
    from src.ingestion.docling_client import DoclingClient
    from src.ingestion.chunker import TokenChunker
    from telegram_bot.services.voyage import VoyageService
    from qdrant_client import QdrantClient

    # Read test file
    test_file = "docs/test_data/ВНЖ Болгарии для фрилансеров： Виза Digital Nomad и путь к гражданству ЕС [cZNAckKrg2g].ru.md"
    with open(test_file, "rb") as f:
        content = f.read()

    # Initialize services
    docling = DoclingClient("http://localhost:5001")
    voyage = VoyageService()
    qdrant = QdrantClient(url="http://localhost:6333")

    service = IngestionService(
        docling_client=docling,
        voyage_client=voyage,
        qdrant_client=qdrant,
        collection_name="test_ingestion",
    )

    # Ingest
    result = await service.ingest_file(
        file_id="test_vnzh_file",
        content=content,
        filename="vnzh_digital_nomad.md",
        folder_id="test_folder",
    )

    assert result["status"] == "indexed"
    assert result["chunk_count"] > 0

    # Verify in Qdrant
    search_result = qdrant.scroll(
        collection_name="test_ingestion",
        scroll_filter={
            "must": [{"key": "file_id", "match": {"value": "test_vnzh_file"}}]
        },
        limit=100,
    )

    assert len(search_result[0]) == result["chunk_count"]

    # Cleanup
    await service.delete_file("test_vnzh_file")
    await docling.close()
```

**Step 2: Commit**

```bash
git add tests/integration/test_ingestion_e2e.py
git commit -m "test(ingestion): add E2E integration test"
```

---

### Task 10: Documentation

**Files:**
- Create: `docs/INGESTION.md`

**Step 1: Create docs**

```markdown
# Document Ingestion Pipeline

## Overview

Production-ready pipeline: Google Drive → Qdrant with incremental updates.

## Architecture

- **CocoIndex**: State management + Google Drive polling
- **Postgres**: Ingestion state storage
- **docling-serve**: Document parsing (PDF, DOCX, etc.)
- **Voyage AI**: Embeddings
- **Qdrant**: Vector storage

## Quick Start

```bash
# 1. Setup
make ingest-setup

# 2. Configure
export GOOGLE_DRIVE_FOLDER_ID=your_folder_id
export GOOGLE_SERVICE_ACCOUNT_KEY_PATH=./credentials/gdrive.json

# 3. Run once
make ingest-run FOLDER_ID=$GOOGLE_DRIVE_FOLDER_ID

# 4. Or continuous
make ingest-continuous FOLDER_ID=$GOOGLE_DRIVE_FOLDER_ID
```

## Supported Formats

| Format | Parser |
|--------|--------|
| PDF | docling (OCR, tables) |
| DOCX | docling |
| XLSX | docling → row chunks |
| Google Docs | Export HTML → docling |
| Google Sheets | Export CSV → row chunks |
| MD/TXT | Direct |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `COCOINDEX_DATABASE_URL` | - | Postgres connection |
| `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` | - | Service account JSON |
| `GOOGLE_DRIVE_FOLDER_ID` | - | Folder to watch |

## Monitoring

```bash
# Check status
make ingest-status

# View logs
docker logs dev-docling -f
```
```

**Step 2: Commit**

```bash
git add docs/INGESTION.md
git commit -m "docs(ingestion): add ingestion pipeline documentation"
```

---

## Verification Checklist

- [ ] `make ingest-setup` runs without errors
- [ ] `make ingest-test` — all unit tests pass
- [ ] `make ingest-run FOLDER_ID=xxx` — processes test files
- [ ] `make ingest-status` — shows indexed files
- [ ] Qdrant has payload indexes for `file_id`, `folder_id`
- [ ] Replace semantics works (re-ingest same file = same chunk count)

---

## Success Criteria

1. **Incremental**: Only changed files re-indexed
2. **Replace semantics**: No orphan chunks after update
3. **Batching**: Voyage calls batched (100 chunks/request)
4. **Error handling**: Failed files go to dead_letter table
5. **Polling**: 60s recent changes + 6h full refresh
