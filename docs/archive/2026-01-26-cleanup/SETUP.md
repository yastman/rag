***REMOVED*** Setup

**Version:** 2.4.0

***REMOVED******REMOVED*** Prerequisites

```bash
python >= 3.9
docker
```

***REMOVED******REMOVED*** Installation

```bash
git clone https://github.com/yastman/rag && cd rag
pip install -e .
cp .env.example .env
```

***REMOVED******REMOVED******REMOVED*** Environment

```bash
***REMOVED*** .env
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
QDRANT_API_KEY=3e7321df905ee908...
QDRANT_URL=http://localhost:6333
```

***REMOVED******REMOVED*** Services

```bash
***REMOVED*** Start Qdrant
docker compose up -d qdrant

***REMOVED*** Verify
curl http://localhost:6333/health
```

***REMOVED******REMOVED*** Index Documents

***REMOVED******REMOVED******REMOVED*** PDF
```python
from src.ingestion.document_parser import DocumentParser
from src.ingestion.chunker import DocumentChunker
from src.ingestion.indexer import DocumentIndexer

parser = DocumentParser()
doc = parser.parse_file("file.pdf")

chunker = DocumentChunker(chunk_size=512, overlap=128)
chunks = chunker.chunk_text(text=doc.content, document_name=doc.filename)

indexer = DocumentIndexer()
indexer.create_collection("collection_name", recreate=False)
await indexer.index_chunks(chunks, "collection_name")
```

***REMOVED******REMOVED******REMOVED*** CSV
```bash
python src/ingestion/csv_to_qdrant.py --input data.csv --collection name
```

***REMOVED******REMOVED*** Search

```python
from src.retrieval.search_engines import HybridRRFColBERTSearchEngine

engine = HybridRRFColBERTSearchEngine()
results = engine.search(query="query text", collection_name="name", limit=5)
```

***REMOVED******REMOVED*** Full Pipeline

```python
from src.core.pipeline import RAGPipeline

pipeline = RAGPipeline()
response = await pipeline.query(question="question", collection="name")
```

***REMOVED******REMOVED*** Verification

```bash
***REMOVED*** Collections
curl -H "api-key: $QDRANT_API_KEY" http://localhost:6333/collections

***REMOVED*** Smoke test
python src/evaluation/smoke_test.py
```
