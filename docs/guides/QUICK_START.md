***REMOVED*** 🚀 QUICK START - Contextual RAG

> **Step-by-step guide for quick start**

***REMOVED******REMOVED*** 5 minutes to first search

***REMOVED******REMOVED******REMOVED*** Step 1: Installation (2 minutes)

```bash
***REMOVED*** 1. Clone repository
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** 2. Create virtual environment
python3.9 -m venv venv
source venv/bin/activate  ***REMOVED*** On Windows: venv\Scripts\activate

***REMOVED*** 3. Install dependencies
pip install -e .

***REMOVED*** 4. Copy configuration
cp .env.example .env
```

***REMOVED******REMOVED******REMOVED*** Step 2: Configuration (1 minute)

**Edit `.env`:**

```env
***REMOVED*** Anthropic Claude API (primary)
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]

***REMOVED*** Qdrant Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  ***REMOVED*** If required

***REMOVED*** OpenAI (optional)
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]

***REMOVED*** Groq (optional)
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** Z.AI (optional)
Z_AI_API_KEY=...
```

***REMOVED******REMOVED******REMOVED*** Step 3: Start Qdrant (1 minute)

```bash
***REMOVED*** Option A: Docker Compose (recommended)
docker compose up -d qdrant

***REMOVED*** Option B: Docker (if no compose)
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  qdrant/qdrant:latest

***REMOVED*** Check
curl http://localhost:6333/health
```

***REMOVED******REMOVED******REMOVED*** Step 4: Create Collection (1 minute)

```bash
***REMOVED*** Create collection with indexes
python create_collection_enhanced.py
```

**Output:**
```
✓ Collection 'legal_documents' created
✓ Indexes created successfully
✓ Ready for ingestion
```

***REMOVED******REMOVED******REMOVED*** Step 5: Load Documents (1 minute)

```bash
***REMOVED*** Load PDF documents from docs/documents/
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents \
  --batch-size 10

***REMOVED*** Or for a single file
python ingestion_contextual_kg_fast.py \
  --pdf-file docs/documents/Constitution_Ukraine.pdf \
  --collection legal_documents
```

**Output:**
```
Loading documents...
✓ 1245 chunks processed
✓ Embeddings created (BGE-M3)
✓ Indexed in Qdrant
```

---

***REMOVED******REMOVED*** First Search (2 minutes)

***REMOVED******REMOVED******REMOVED*** Option A: Python Script

**test_api_quick.py:**
```bash
python test_api_quick.py
```

**Or manually:**

```python
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

***REMOVED*** Connect to Qdrant
client = QdrantClient(QDRANT_URL)

***REMOVED*** Search
query = "What rights do Ukrainian citizens have?"
results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=[0.1, 0.2, ...],  ***REMOVED*** Query embedding
    limit=5
)

for result in results:
    print(f"Topic: {result.payload['title']}")
    print(f"Text: {result.payload['text'][:200]}...")
    print(f"Score: {result.score}\n")
```

***REMOVED******REMOVED******REMOVED*** Option B: CLI Command

```bash
python example_search.py \
  --query "What rights do Ukrainian citizens have?" \
  --top-k 5
```

**Expected result:**
```
Search results (DBSF):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. [0.9636] Section II. Rights and Freedoms of Man and Citizen
   Constitution of Ukraine, art. 28-68

2. [0.9402] Basic Rights of Citizens
   Civil Code, art. 1-10

3. [0.9187] Protection of Citizens' Rights
   Criminal Code, art. 100-150
```

---

***REMOVED******REMOVED*** Testing (2 minutes)

***REMOVED******REMOVED******REMOVED*** Smoke Test

```bash
***REMOVED*** Quick check of all components
python evaluation/smoke_test.py

***REMOVED*** Result
✓ Qdrant connection OK
✓ Claude API OK
✓ Embeddings OK
✓ Search OK
```

***REMOVED******REMOVED******REMOVED*** A/B Testing

```bash
***REMOVED*** Run A/B test (logging to MLflow)
python evaluation/run_ab_test.py \
  --queries evaluation/data/test_queries.txt \
  --baseline baseline \
  --challenger dbsf

***REMOVED*** Results
BASELINE:  Recall@1=91.3%, NDCG@10=0.9619
DBSF:      Recall@1=94.0%, NDCG@10=0.9711
IMPROVEMENT: +2.9% Recall, +1.0% NDCG
```

---

***REMOVED******REMOVED*** Monitoring (optional)

***REMOVED******REMOVED******REMOVED*** MLflow Dashboard

```bash
***REMOVED*** Start MLflow server
docker compose --profile ml up -d mlflow

***REMOVED*** Open in browser
open http://localhost:5000
```

**What you'll see:**
- All running experiments
- Metrics (Recall, NDCG, Latency)
- Comparison between runs
- Configuration parameters

***REMOVED******REMOVED******REMOVED*** Langfuse Dashboard

```bash
***REMOVED*** Start Langfuse
docker compose --profile ml up -d langfuse

***REMOVED*** Open in browser
open http://localhost:3001
```

**What you'll see:**
- All LLM requests and responses
- Latency and token count
- Errors and exceptions
- Usage analytics

---

***REMOVED******REMOVED*** Frequently Asked Questions

***REMOVED******REMOVED******REMOVED*** Q: How to add new documents?

```bash
***REMOVED*** Simply add PDF to docs/documents/
cp my_document.pdf docs/documents/

***REMOVED*** And run ingestion again
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

***REMOVED******REMOVED******REMOVED*** Q: How to select another LLM (OpenAI, Groq)?

**Option 1: Via config.py**
```python
API_PROVIDER = 'openai'  ***REMOVED*** Or 'groq', 'zai'
MODEL_NAME = 'gpt-4-turbo-preview'
```

**Option 2: Via environment variable**
```bash
export API_PROVIDER=groq
python test_api_quick.py
```

***REMOVED******REMOVED******REMOVED*** Q: How to improve search quality?

1. **Use DBSF instead of baseline search**
   ```python
   from evaluation.search_engines import DBSFSearchEngine
   engine = DBSFSearchEngine()
   ```

2. **Increase document context**
   ```python
   ***REMOVED*** In config.py
   CHUNK_SIZE = 1024  ***REMOVED*** Instead of 512
   ```

3. **Add more documents**
   ```bash
   python ingestion_contextual_kg_fast.py --pdf-path /more/docs
   ```

***REMOVED******REMOVED******REMOVED*** Q: How to run on production server?

```bash
***REMOVED*** 1. Use production configuration
export ENV=production
export QDRANT_URL=https://qdrant.example.com
export QDRANT_API_KEY=your-secure-key

***REMOVED*** 2. Use WSGI server (Gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:application

***REMOVED*** 3. Use SSL certificate
***REMOVED*** Configure nginx/reverse proxy
```

***REMOVED******REMOVED******REMOVED*** Q: How to clear data?

```bash
***REMOVED*** Delete Qdrant collection
python -c "
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

client = QdrantClient(QDRANT_URL)
client.delete_collection(COLLECTION_NAME)
"

***REMOVED*** Or simply restart Qdrant
docker compose down qdrant
docker compose up -d qdrant
```

---

***REMOVED******REMOVED*** Common Errors and Solutions

| Error | Cause | Solution |
|--------|---------|---------|
| `ConnectionError: localhost:6333` | Qdrant not running | `docker compose up -d qdrant` |
| `APIError: invalid_request_error` | Invalid API key | Check `.env` ANTHROPIC_API_KEY |
| `ModuleNotFoundError: qdrant_client` | Dependencies not installed | `pip install -e .` |
| `TimeoutError` during loading | PDF too large | Use `--batch-size 5` |
| Low search metrics | Documents not indexed | Run ingestion again |

---

***REMOVED******REMOVED*** Next Steps

1. **Read PROJECT_STRUCTURE.md** - Complete description of all modules
2. **Study ARCHITECTURE.md** - System architecture
3. **Run evaluation/run_ab_test.py** - A/B testing
4. **Try different LLMs** - OpenAI, Groq, Z.AI
5. **Monitor metrics** - MLflow and Langfuse dashboards

---

***REMOVED******REMOVED*** Production Readiness Checklist

- [ ] All API keys configured in `.env`
- [ ] Qdrant running and accessible
- [ ] Documents loaded and indexed
- [ ] Smoke test passed (`evaluation/smoke_test.py`)
- [ ] A/B test shows expected metrics
- [ ] MLflow/Langfuse configured for monitoring
- [ ] SSL certificate installed (for production)
- [ ] Data backups configured
- [ ] Documentation updated for your team

---

***REMOVED******REMOVED*** Useful Commands

```bash
***REMOVED*** Project information
python list_available_models.py          ***REMOVED*** List available models
python check_sparse_vectors.py           ***REMOVED*** Check sparse vectors

***REMOVED*** Testing
python test_api_quick.py                 ***REMOVED*** Smoke test
python test_api_safe.py                  ***REMOVED*** Safe test
python evaluation/smoke_test.py          ***REMOVED*** Full smoke test

***REMOVED*** Evaluation
python evaluation/run_ab_test.py         ***REMOVED*** A/B test with logging
python evaluation/evaluate_with_ragas.py ***REMOVED*** RAGAS evaluation

***REMOVED*** Development
ruff check .                             ***REMOVED*** Lint check
ruff format .                            ***REMOVED*** Formatting
mypy . --ignore-missing-imports          ***REMOVED*** Type checking
python -m pytest tests/                  ***REMOVED*** Unit tests (if available)
```

---

**Last Updated**: 2024-10-29
**Version**: 2.0.1
**Repository**: https://github.com/yastman/rag
