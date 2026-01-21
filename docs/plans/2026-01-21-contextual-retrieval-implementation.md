# Contextual Retrieval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Contextual Retrieval (Anthropic approach) to RAG pipeline for +35-49% retrieval accuracy improvement.

**Architecture:** Claude Code CLI (Opus 4.5) обрабатывает VTT → выдаёт JSON → Python скрипт индексирует в Qdrant через существующий DocumentIndexer. Claude CLI делает всю LLM работу (очистка, chunking, context).

**Tech Stack:** Python 3.11+, pytest, Qdrant, BGE-M3, Claude Code CLI (Opus 4.5)

---

## Task 0: Prerequisites Check

**Goal:** Убедиться что Qdrant запущен и настроен перед началом работы.

**Step 1: Check environment variables**

Проверить `.env` файл:

```bash
cat .env | grep -E "(QDRANT|COLLECTION)"
```

Expected output (примерно):
```
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
COLLECTION_NAME=legal_documents
```

**Step 2: Check Qdrant is running**

```bash
curl -s http://localhost:6333/collections | python -m json.tool
```

Expected: JSON с списком коллекций (может быть пустой `{"collections": []}`)

If error "Connection refused":
```bash
# Если Qdrant в Docker:
docker ps | grep qdrant
docker start qdrant  # если остановлен

# Или запустить:
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

**Step 3: Run existing connection test**

```bash
pytest tests/test_qdrant_connection.py -v
```

Expected: All tests PASS

**Step 4: Verify BGE-M3 model loads**

```bash
python -c "from src.models import get_bge_m3_model; m = get_bge_m3_model(); print('BGE-M3 OK')"
```

Expected: "BGE-M3 OK" (первый запуск скачает модель ~2GB)

**If any step fails:** Fix before proceeding to Task 1.

---

## Task 1: JSON Schema для Contextual Chunks

**Files:**
- Create: `src/ingestion/contextual_schema.py`
- Test: `tests/test_contextual_schema.py`

**Step 1: Write the failing test**

```python
# tests/test_contextual_schema.py
"""Tests for Contextual Retrieval JSON schema."""

import json
import pytest

from src.ingestion.contextual_schema import (
    ContextualChunk,
    ContextualDocument,
    create_text_for_embedding,
)


class TestContextualChunk:
    """Tests for ContextualChunk dataclass."""

    def test_chunk_creation(self):
        """Chunk should store all required fields."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Цены на недвижимость",
            keywords=["Бургас", "цены", "евро"],
            context="Этот фрагмент о ценах на квартиры в Болгарии.",
            text="В Бургасе цены начинаются от 50000 евро.",
        )
        assert chunk.chunk_id == 1
        assert chunk.topic == "Цены на недвижимость"
        assert len(chunk.keywords) == 3
        assert "Бургас" in chunk.keywords

    def test_chunk_text_for_embedding(self):
        """text_for_embedding should combine context and text."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["слово"],
            context="Контекст чанка.",
            text="Основной текст.",
        )
        embedding_text = chunk.text_for_embedding
        assert "# Тема" in embedding_text
        assert "Контекст чанка." in embedding_text
        assert "Основной текст." in embedding_text

    def test_chunk_to_dict(self):
        """Chunk should serialize to dict."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["a", "b"],
            context="Контекст",
            text="Текст",
        )
        d = chunk.to_dict()
        assert d["chunk_id"] == 1
        assert d["topic"] == "Тема"
        assert "text_for_embedding" in d


class TestContextualDocument:
    """Tests for ContextualDocument dataclass."""

    def test_document_creation(self):
        """Document should store source and chunks."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["слово"],
            context="Контекст",
            text="Текст",
        )
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[chunk],
        )
        assert doc.source == "video.vtt"
        assert len(doc.chunks) == 1
        assert doc.total_chunks == 1

    def test_document_to_json(self):
        """Document should serialize to valid JSON."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["слово"],
            context="Контекст",
            text="Текст",
        )
        doc = ContextualDocument(source="video.vtt", chunks=[chunk])
        json_str = doc.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["source"] == "video.vtt"
        assert parsed["total_chunks"] == 1
        assert "processed_at" in parsed

    def test_document_from_json(self):
        """Document should deserialize from JSON."""
        json_str = '''{
            "source": "test.vtt",
            "processed_at": "2026-01-21T12:00:00",
            "total_chunks": 1,
            "chunks": [{
                "chunk_id": 1,
                "topic": "Тема",
                "keywords": ["a"],
                "context": "Контекст",
                "text": "Текст",
                "text_for_embedding": "# Тема\\n\\nКонтекст\\n\\nТекст"
            }]
        }'''
        doc = ContextualDocument.from_json(json_str)
        assert doc.source == "test.vtt"
        assert len(doc.chunks) == 1
        assert doc.chunks[0].topic == "Тема"


class TestCreateTextForEmbedding:
    """Tests for text_for_embedding generation."""

    def test_creates_markdown_format(self):
        """Should create Markdown-formatted text."""
        result = create_text_for_embedding(
            topic="Цены в Бургасе",
            context="Обсуждение цен на недвижимость.",
            text="Цены начинаются от 50000 евро.",
        )
        assert result.startswith("# Цены в Бургасе")
        assert "Обсуждение цен" in result
        assert "50000 евро" in result

    def test_handles_empty_context(self):
        """Should handle empty context gracefully."""
        result = create_text_for_embedding(
            topic="Тема",
            context="",
            text="Текст чанка.",
        )
        assert "# Тема" in result
        assert "Текст чанка." in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_contextual_schema.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.ingestion.contextual_schema'"

**Step 3: Write minimal implementation**

```python
# src/ingestion/contextual_schema.py
"""JSON schema for Contextual Retrieval chunks.

Defines dataclasses for storing contextualized chunks created by Claude CLI:
- LLM-generated context (Anthropic Contextual Retrieval)
- Extracted metadata (topic, keywords)
- Formatted text for embedding

Claude CLI creates JSON in this format, Python code loads and indexes it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


def create_text_for_embedding(topic: str, context: str, text: str) -> str:
    """
    Create Markdown-formatted text for embedding.

    Format:
    # {topic}

    {context}

    {text}

    Args:
        topic: Main topic of the chunk
        context: LLM-generated context
        text: Original chunk text

    Returns:
        Formatted Markdown string
    """
    parts = [f"# {topic}"]

    if context and context.strip():
        parts.append(f"\n{context}")

    parts.append(f"\n{text}")

    return "\n".join(parts)


@dataclass
class ContextualChunk:
    """A chunk with LLM-generated context and metadata.

    Created by Claude CLI during Contextual Retrieval processing.
    """

    chunk_id: int
    topic: str
    keywords: list[str]
    context: str
    text: str
    _text_for_embedding: Optional[str] = field(default=None, repr=False)

    @property
    def text_for_embedding(self) -> str:
        """Get or generate text formatted for embedding."""
        if self._text_for_embedding is None:
            self._text_for_embedding = create_text_for_embedding(
                topic=self.topic,
                context=self.context,
                text=self.text,
            )
        return self._text_for_embedding

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "topic": self.topic,
            "keywords": self.keywords,
            "context": self.context,
            "text": self.text,
            "text_for_embedding": self.text_for_embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextualChunk":
        """Deserialize from dictionary."""
        return cls(
            chunk_id=data["chunk_id"],
            topic=data["topic"],
            keywords=data["keywords"],
            context=data["context"],
            text=data["text"],
            _text_for_embedding=data.get("text_for_embedding"),
        )


@dataclass
class ContextualDocument:
    """A document with contextualized chunks.

    JSON file created by Claude CLI, loaded by Python for indexing.
    """

    source: str
    chunks: list[ContextualChunk]
    processed_at: Optional[str] = None

    def __post_init__(self):
        if self.processed_at is None:
            self.processed_at = datetime.utcnow().isoformat()

    @property
    def total_chunks(self) -> int:
        """Total number of chunks."""
        return len(self.chunks)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "source": self.source,
            "processed_at": self.processed_at,
            "total_chunks": self.total_chunks,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, file_path: str) -> None:
        """Save to JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: dict) -> "ContextualDocument":
        """Deserialize from dictionary."""
        chunks = [ContextualChunk.from_dict(c) for c in data["chunks"]]
        return cls(
            source=data["source"],
            chunks=chunks,
            processed_at=data.get("processed_at"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ContextualDocument":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def load(cls, file_path: str) -> "ContextualDocument":
        """Load from JSON file."""
        with open(file_path, encoding="utf-8") as f:
            return cls.from_json(f.read())
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_contextual_schema.py -v`
Expected: All tests PASS

**Step 5: Update module exports**

Modify `src/ingestion/__init__.py` - add imports:

```python
from .contextual_schema import (
    ContextualChunk,
    ContextualDocument,
    create_text_for_embedding,
)
```

Add to `__all__` list:
```python
"ContextualChunk",
"ContextualDocument",
"create_text_for_embedding",
```

**Step 6: Commit**

```bash
git add src/ingestion/contextual_schema.py tests/test_contextual_schema.py src/ingestion/__init__.py
git commit -m "$(cat <<'EOF'
feat(ingestion): add Contextual Retrieval JSON schema

- ContextualChunk: chunk with topic, keywords, context, text
- ContextualDocument: collection of chunks with metadata
- create_text_for_embedding: Markdown formatting for BGE-M3
- JSON serialization/deserialization support

Schema for Claude CLI output → Python indexing pipeline.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Loader для конвертации JSON → Chunk

**Files:**
- Create: `src/ingestion/contextual_loader.py`
- Test: `tests/test_contextual_loader.py`

**Step 1: Write the failing test**

```python
# tests/test_contextual_loader.py
"""Tests for loading contextual chunks into existing pipeline."""

import pytest

from src.ingestion.contextual_loader import load_contextual_chunks, load_contextual_json
from src.ingestion.contextual_schema import ContextualChunk, ContextualDocument
from src.ingestion.chunker import Chunk


class TestLoadContextualChunks:
    """Tests for load_contextual_chunks function."""

    def test_converts_to_chunk_objects(self):
        """Should convert ContextualDocument to list of Chunk objects."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Тема",
                    keywords=["слово"],
                    context="Контекст",
                    text="Текст",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        assert len(chunks) == 1
        assert isinstance(chunks[0], Chunk)

    def test_uses_text_for_embedding(self):
        """Chunk.text should be the contextualized text_for_embedding."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Цены",
                    keywords=["евро"],
                    context="Контекст о ценах.",
                    text="50000 евро.",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        # Should use text_for_embedding, not raw text
        assert "# Цены" in chunks[0].text
        assert "Контекст о ценах" in chunks[0].text
        assert "50000 евро" in chunks[0].text

    def test_preserves_metadata(self):
        """extra_metadata should contain topic, keywords, original_text."""
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Недвижимость",
                    keywords=["Болгария", "цены"],
                    context="Контекст",
                    text="Оригинальный текст",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        meta = chunks[0].extra_metadata
        assert meta["topic"] == "Недвижимость"
        assert meta["keywords"] == ["Болгария", "цены"]
        assert meta["original_text"] == "Оригинальный текст"
        assert meta["context"] == "Контекст"
        assert meta["source_type"] == "vtt_contextual"

    def test_sets_document_name(self):
        """document_name should be the source filename."""
        doc = ContextualDocument(
            source="my_video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="T",
                    keywords=["k"],
                    context="C",
                    text="X",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        assert chunks[0].document_name == "my_video.vtt"

    def test_handles_multiple_chunks(self):
        """Should handle documents with multiple chunks."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(chunk_id=i, topic=f"T{i}", keywords=[], context="", text=f"Text {i}")
                for i in range(5)
            ],
        )
        chunks = load_contextual_chunks(doc)

        assert len(chunks) == 5
        assert chunks[0].chunk_id == 0
        assert chunks[4].chunk_id == 4


class TestLoadContextualJson:
    """Tests for load_contextual_json function."""

    def test_loads_from_file(self, tmp_path):
        """Should load JSON file and convert to Chunks."""
        # Create test JSON
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Тест",
                    keywords=["test"],
                    context="Test context",
                    text="Test text",
                )
            ],
        )
        json_file = tmp_path / "test.json"
        doc.save(str(json_file))

        # Load and convert
        chunks = load_contextual_json(str(json_file))

        assert len(chunks) == 1
        assert isinstance(chunks[0], Chunk)
        assert "# Тест" in chunks[0].text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_contextual_loader.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.ingestion.contextual_loader'"

**Step 3: Write minimal implementation**

```python
# src/ingestion/contextual_loader.py
"""Load contextual chunks into existing RAG pipeline.

Converts ContextualDocument objects (JSON from Claude CLI)
into Chunk objects compatible with DocumentIndexer.
"""

from .chunker import Chunk
from .contextual_schema import ContextualDocument


def load_contextual_chunks(doc: ContextualDocument) -> list[Chunk]:
    """
    Convert ContextualDocument to list of Chunk objects.

    Uses text_for_embedding (contextualized text) as the main text
    for BGE-M3 embedding. Preserves original text and metadata
    in extra_metadata for retrieval display.

    Args:
        doc: ContextualDocument from Claude CLI JSON output

    Returns:
        List of Chunk objects ready for DocumentIndexer
    """
    chunks: list[Chunk] = []

    for ctx_chunk in doc.chunks:
        chunk = Chunk(
            text=ctx_chunk.text_for_embedding,
            chunk_id=ctx_chunk.chunk_id,
            document_name=doc.source,
            article_number=f"chunk_{ctx_chunk.chunk_id}",
            extra_metadata={
                "topic": ctx_chunk.topic,
                "keywords": ctx_chunk.keywords,
                "original_text": ctx_chunk.text,
                "context": ctx_chunk.context,
                "source_type": "vtt_contextual",
            },
        )
        chunks.append(chunk)

    return chunks


def load_contextual_json(json_path: str) -> list[Chunk]:
    """
    Load contextual chunks from JSON file.

    Convenience function that loads Claude CLI JSON output
    and converts to Chunks ready for indexing.

    Args:
        json_path: Path to JSON file created by Claude CLI

    Returns:
        List of Chunk objects ready for DocumentIndexer
    """
    doc = ContextualDocument.load(json_path)
    return load_contextual_chunks(doc)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_contextual_loader.py -v`
Expected: All tests PASS

**Step 5: Update module exports**

Modify `src/ingestion/__init__.py` - add imports:

```python
from .contextual_loader import load_contextual_chunks, load_contextual_json
```

Add to `__all__` list:
```python
"load_contextual_chunks",
"load_contextual_json",
```

**Step 6: Commit**

```bash
git add src/ingestion/contextual_loader.py tests/test_contextual_loader.py src/ingestion/__init__.py
git commit -m "$(cat <<'EOF'
feat(ingestion): add contextual chunks loader

- load_contextual_chunks: convert ContextualDocument to Chunk list
- load_contextual_json: load Claude CLI JSON → Chunks
- Preserves metadata (topic, keywords) in extra_metadata
- Uses text_for_embedding for BGE-M3 vectorization

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Indexing Script

**Files:**
- Create: `scripts/index_contextual.py`

**Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Index contextual JSON files into Qdrant.

Takes JSON files created by Claude CLI (with Contextual Retrieval)
and indexes them using the existing DocumentIndexer pipeline.

Usage:
    python scripts/index_contextual.py docs/processed/video1.json
    python scripts/index_contextual.py docs/processed/*.json --collection contextual_demo
    python scripts/index_contextual.py docs/processed/ --recreate
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Settings
from src.ingestion import DocumentIndexer, load_contextual_json


async def index_file(
    indexer: DocumentIndexer,
    json_path: Path,
    collection_name: str,
) -> dict:
    """Index a single contextual JSON file."""
    print(f"\nIndexing: {json_path.name}")

    # Load chunks from JSON
    chunks = load_contextual_json(str(json_path))
    print(f"  Loaded {len(chunks)} chunks")

    # Index chunks
    stats = await indexer.index_chunks(chunks, collection_name)

    return {
        "file": json_path.name,
        "total_chunks": stats.total_chunks,
        "indexed_chunks": stats.indexed_chunks,
        "failed_chunks": stats.failed_chunks,
    }


async def main(args: argparse.Namespace) -> int:
    """Main entry point."""
    print("\n" + "=" * 60)
    print("Contextual Retrieval Indexer")
    print("=" * 60)

    # Initialize
    settings = Settings()
    indexer = DocumentIndexer(settings)

    collection_name = args.collection or settings.collection_name
    print(f"\nCollection: {collection_name}")

    # Create collection if needed
    if args.recreate:
        print(f"Recreating collection: {collection_name}")
    indexer.create_collection(collection_name, recreate=args.recreate)

    # Find JSON files
    input_path = Path(args.input)
    if input_path.is_file():
        json_files = [input_path]
    elif input_path.is_dir():
        json_files = list(input_path.glob("*.json"))
    else:
        # Glob pattern
        json_files = list(Path(".").glob(args.input))

    if not json_files:
        print(f"Error: No JSON files found: {args.input}")
        return 1

    print(f"Found {len(json_files)} JSON file(s)")

    # Index each file
    results = []
    for json_path in json_files:
        try:
            result = await index_file(indexer, json_path, collection_name)
            results.append(result)
        except Exception as e:
            print(f"  Error: {e}")
            results.append({
                "file": json_path.name,
                "error": str(e),
            })

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    total_indexed = sum(r.get("indexed_chunks", 0) for r in results)
    total_failed = sum(r.get("failed_chunks", 0) for r in results)

    for r in results:
        if "error" in r:
            print(f"  {r['file']}: ERROR - {r['error']}")
        else:
            print(f"  {r['file']}: {r['indexed_chunks']} chunks indexed")

    print(f"\nTotal: {total_indexed} indexed, {total_failed} failed")

    # Print collection stats
    stats = indexer.get_collection_stats(collection_name)
    if stats:
        print(f"\nCollection '{collection_name}': {stats.get('points_count', 0)} total points")

    return 0 if total_failed == 0 else 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Index contextual JSON files into Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "input",
        help="JSON file, directory, or glob pattern",
    )

    parser.add_argument(
        "--collection", "-c",
        help="Target collection name (default: from settings)",
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate collection if exists",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args)))
```

**Step 2: Commit**

```bash
git add scripts/index_contextual.py
git commit -m "$(cat <<'EOF'
feat(scripts): add contextual JSON indexer

- Index JSON files from Claude CLI processing
- Support single file, directory, or glob pattern
- Uses existing DocumentIndexer pipeline
- Option to recreate collection

Usage: python scripts/index_contextual.py docs/processed/*.json

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Claude CLI Prompts Documentation

**Files:**
- Create: `docs/processed/README.md`
- Create: `docs/processed/.gitkeep`

**Step 1: Create directory**

```bash
mkdir -p docs/processed
touch docs/processed/.gitkeep
```

**Step 2: Create README with Claude CLI prompts**

```markdown
# Processed Documents

JSON files created by Claude Code CLI for Contextual Retrieval indexing.

## Workflow

### Step 1: Process VTT with Claude CLI

Open Claude Code CLI in project directory and run:

```
Прочитай файл docs/test_data/[название].vtt

Обработай через Contextual Retrieval:
1. Очисти текст от таймкодов и VTT метаданных
2. Разбей на семантические чанки (LLM решает размер)
3. Для каждого чанка:
   - Добавь context (1-2 предложения о чём этот фрагмент в контексте всего документа)
   - Извлеки topic (3-5 слов)
   - Извлеки keywords (3-7 ключевых слов)

Сохрани результат в docs/processed/[название].json по схеме:

{
  "source": "filename.vtt",
  "processed_at": "ISO timestamp",
  "total_chunks": N,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Тема чанка",
      "keywords": ["слово1", "слово2"],
      "context": "Этот фрагмент из видео о... Обсуждается...",
      "text": "Оригинальный текст чанка",
      "text_for_embedding": "# Тема чанка\n\nКонтекст\n\nТекст"
    }
  ]
}
```

### Step 2: Index into Qdrant

```bash
python scripts/index_contextual.py docs/processed/[название].json --collection contextual_demo
```

### Step 3: Test Search

```python
from src.core.pipeline import RAGPipeline
import asyncio

pipeline = RAGPipeline()
result = asyncio.run(pipeline.search("Ваш запрос"))

for r in result.results:
    print(f"Topic: {r['metadata'].get('topic')}")
    print(f"Score: {r['score']:.3f}")
    print(f"Text: {r['text'][:200]}...")
    print()
```

## JSON Schema

See `src/ingestion/contextual_schema.py` for Python dataclasses.

| Field | Type | Description |
|-------|------|-------------|
| source | string | Original VTT filename |
| processed_at | string | ISO timestamp |
| total_chunks | int | Number of chunks |
| chunks[].chunk_id | int | Sequential ID |
| chunks[].topic | string | Main topic (3-5 words) |
| chunks[].keywords | array | Search keywords |
| chunks[].context | string | LLM-generated context |
| chunks[].text | string | Original chunk text |
| chunks[].text_for_embedding | string | Formatted for BGE-M3 |

## Example

```json
{
  "source": "Как купить квартиру в Болгарии.vtt",
  "processed_at": "2026-01-21T12:00:00",
  "total_chunks": 3,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Введение в покупку недвижимости",
      "keywords": ["Болгария", "недвижимость", "покупка", "апартамент"],
      "context": "Это вступительная часть видео о покупке недвижимости в Болгарии. Автор представляется и описывает тематику видео.",
      "text": "Покупка апартамента в Болгарии возле моря. В этом видео я расскажу вам всё: дёшево или дорого, ловушка или безопасность?",
      "text_for_embedding": "# Введение в покупку недвижимости\n\nЭто вступительная часть видео о покупке недвижимости в Болгарии. Автор представляется и описывает тематику видео.\n\nПокупка апартамента в Болгарии возле моря. В этом видео я расскажу вам всё: дёшево или дорого, ловушка или безопасность?"
    }
  ]
}
```
```

**Step 3: Commit**

```bash
git add docs/processed/
git commit -m "$(cat <<'EOF'
docs: add Claude CLI prompts for Contextual Retrieval

- docs/processed/ directory for JSON output
- README with step-by-step workflow
- Example prompts for Claude Code CLI
- JSON schema documentation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Integration Test

**Files:**
- Create: `tests/test_contextual_integration.py`

**Step 1: Write integration test**

```python
# tests/test_contextual_integration.py
"""Integration tests for Contextual Retrieval pipeline."""

import json
import pytest
from pathlib import Path

from src.ingestion import (
    ContextualChunk,
    ContextualDocument,
    load_contextual_chunks,
    load_contextual_json,
)
from src.ingestion.chunker import Chunk


class TestContextualPipeline:
    """Test full pipeline from JSON to indexer-ready Chunks."""

    def test_json_round_trip(self, tmp_path):
        """Document should serialize and deserialize correctly."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Недвижимость в Болгарии",
                    keywords=["Болгария", "недвижимость", "покупка"],
                    context="Видео о покупке недвижимости в Болгарии.",
                    text="Покупка апартамента в Болгарии возле моря.",
                )
            ],
        )

        # Save
        json_file = tmp_path / "test.json"
        doc.save(str(json_file))

        # Load
        loaded = ContextualDocument.load(str(json_file))

        assert loaded.source == "test.vtt"
        assert len(loaded.chunks) == 1
        assert loaded.chunks[0].topic == "Недвижимость в Болгарии"

    def test_json_to_indexer_chunks(self, tmp_path):
        """JSON file should convert to indexer-compatible Chunks."""
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Цены",
                    keywords=["евро", "цены"],
                    context="Контекст о ценах.",
                    text="50000 евро за студию.",
                ),
                ContextualChunk(
                    chunk_id=2,
                    topic="Локации",
                    keywords=["Бургас", "море"],
                    context="Контекст о локациях.",
                    text="Бургас у моря.",
                ),
            ],
        )

        # Save and load via function
        json_file = tmp_path / "video.json"
        doc.save(str(json_file))
        chunks = load_contextual_json(str(json_file))

        assert len(chunks) == 2
        assert all(isinstance(c, Chunk) for c in chunks)

        # Check first chunk
        assert "# Цены" in chunks[0].text
        assert chunks[0].extra_metadata["topic"] == "Цены"
        assert chunks[0].document_name == "video.vtt"

    def test_text_for_embedding_format(self):
        """text_for_embedding should be properly formatted Markdown."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Недвижимость в Болгарии",
            keywords=["Болгария"],
            context="Этот фрагмент из видео о покупке недвижимости.",
            text="Покупка апартамента возле моря.",
        )

        text = chunk.text_for_embedding

        # Should be Markdown format
        lines = text.split("\n")
        assert lines[0] == "# Недвижимость в Болгарии"
        assert "Этот фрагмент из видео" in text
        assert "Покупка апартамента" in text

    def test_metadata_preserved_for_search_display(self):
        """Original text should be in metadata for search result display."""
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Тема",
                    keywords=["ключ"],
                    context="Контекст для embedding.",
                    text="Оригинальный текст для отображения.",
                )
            ],
        )

        chunks = load_contextual_chunks(doc)

        # text_for_embedding used for vectorization
        assert "# Тема" in chunks[0].text
        assert "Контекст для embedding" in chunks[0].text

        # Original text preserved for display
        assert chunks[0].extra_metadata["original_text"] == "Оригинальный текст для отображения."


class TestExampleJson:
    """Test with example JSON structure."""

    def test_parses_example_json(self, tmp_path):
        """Should parse JSON in documented format."""
        example_json = '''{
  "source": "Как купить квартиру в Болгарии.vtt",
  "processed_at": "2026-01-21T12:00:00",
  "total_chunks": 2,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Введение в покупку недвижимости",
      "keywords": ["Болгария", "недвижимость", "покупка"],
      "context": "Вступительная часть видео о покупке недвижимости.",
      "text": "Покупка апартамента в Болгарии возле моря.",
      "text_for_embedding": "# Введение\\n\\nВступительная часть\\n\\nПокупка апартамента"
    },
    {
      "chunk_id": 2,
      "topic": "Цены на недвижимость",
      "keywords": ["цены", "евро", "Бургас"],
      "context": "Обсуждение цен на квартиры в разных городах.",
      "text": "В Бургасе цены начинаются от 50000 евро.",
      "text_for_embedding": "# Цены\\n\\nОбсуждение цен\\n\\nВ Бургасе цены"
    }
  ]
}'''
        json_file = tmp_path / "example.json"
        json_file.write_text(example_json, encoding="utf-8")

        chunks = load_contextual_json(str(json_file))

        assert len(chunks) == 2
        assert chunks[0].extra_metadata["topic"] == "Введение в покупку недвижимости"
        assert chunks[1].extra_metadata["topic"] == "Цены на недвижимость"
        assert "Бургас" in chunks[1].extra_metadata["keywords"]
```

**Step 2: Run integration tests**

Run: `pytest tests/test_contextual_integration.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_contextual_integration.py
git commit -m "$(cat <<'EOF'
test: add Contextual Retrieval integration tests

- JSON round-trip serialization
- JSON to indexer Chunks conversion
- text_for_embedding Markdown format
- Metadata preservation for search display
- Example JSON parsing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 0 | Prerequisites Check | Qdrant, BGE-M3, .env |
| 1 | JSON Schema | `src/ingestion/contextual_schema.py` |
| 2 | Loader | `src/ingestion/contextual_loader.py` |
| 3 | Indexing Script | `scripts/index_contextual.py` |
| 4 | Claude CLI Docs | `docs/processed/README.md` |
| 5 | Integration Tests | `tests/test_contextual_integration.py` |

## Full Workflow After Implementation

```
┌─────────────────────────────────────────────────────────────┐
│  1. Claude Code CLI (терминал)                              │
│                                                             │
│  Промпт из docs/processed/README.md                         │
│  Input: docs/test_data/video.vtt                            │
│  Output: docs/processed/video.json                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Python Script (терминал)                                │
│                                                             │
│  python scripts/index_contextual.py \                       │
│      docs/processed/video.json \                            │
│      --collection contextual_demo                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  3. Qdrant (автоматически)                                  │
│                                                             │
│  JSON → Chunks → BGE-M3 → Dense + Sparse + ColBERT → Store  │
└─────────────────────────────────────────────────────────────┘
```

## Verification

After all tasks, run:

```bash
pytest tests/test_contextual_schema.py tests/test_contextual_loader.py tests/test_contextual_integration.py -v
```

All tests should PASS.
