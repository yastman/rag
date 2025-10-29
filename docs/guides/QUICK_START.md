# 🚀 QUICK START - Contextual RAG

> **Step-by-step guide for quick start**

## 5 minutes to first search

### Step 1: Installation (2 minutes)

```bash
# 1. Clone repository
git clone https://github.com/yastman/rag.git
cd rag

# 2. Create virtual environment
python3.9 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e .

# 4. Copy configuration
cp .env.example .env
```

### Step 2: Configuration (1 minute)

**Edit `.env`:**

```env
# Anthropic Claude API (primary)
ANTHROPIC_API_KEY=sk-ant-...

# Qdrant Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # If required

# OpenAI (optional)
OPENAI_API_KEY=sk-...

# Groq (optional)
GROQ_API_KEY=gsk_...

# Z.AI (optional)
Z_AI_API_KEY=...
```

### Step 3: Start Qdrant (1 minute)

```bash
# Option A: Docker Compose (recommended)
docker compose up -d qdrant

# Option B: Docker (if no compose)
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  qdrant/qdrant:latest

# Check
curl http://localhost:6333/health
```

### Step 4: Create Collection (1 minute)

```bash
# Create collection with indexes
python create_collection_enhanced.py
```

**Output:**
```
✓ Collection 'legal_documents' created
✓ Indexes created successfully
✓ Ready for ingestion
```

### Step 5: Load Documents (1 minute)

```bash
# Load PDF documents from docs/documents/
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents \
  --batch-size 10

# Or for a single file
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

## First Search (2 minutes)

### Option A: Python Script

**test_api_quick.py:**
```bash
python test_api_quick.py
```

**Or manually:**

```python
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

# Connect to Qdrant
client = QdrantClient(QDRANT_URL)

# Search
query = "What rights do Ukrainian citizens have?"
results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=[0.1, 0.2, ...],  # Query embedding
    limit=5
)

for result in results:
    print(f"Topic: {result.payload['title']}")
    print(f"Text: {result.payload['text'][:200]}...")
    print(f"Score: {result.score}\n")
```

### Option B: CLI Command

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

## Testing (2 minutes)

### Smoke Test

```bash
# Quick check of all components
python evaluation/smoke_test.py

# Result
✓ Qdrant connection OK
✓ Claude API OK
✓ Embeddings OK
✓ Search OK
```

### A/B Testing

```bash
# Run A/B test (logging to MLflow)
python evaluation/run_ab_test.py \
  --queries evaluation/data/test_queries.txt \
  --baseline baseline \
  --challenger dbsf

# Results
BASELINE:  Recall@1=91.3%, NDCG@10=0.9619
DBSF:      Recall@1=94.0%, NDCG@10=0.9711
IMPROVEMENT: +2.9% Recall, +1.0% NDCG
```

---

## Monitoring (optional)

### MLflow Dashboard

```bash
# Start MLflow server
docker compose --profile ml up -d mlflow

# Open in browser
open http://localhost:5000
```

**What you'll see:**
- All running experiments
- Metrics (Recall, NDCG, Latency)
- Comparison between runs
- Configuration parameters

### Langfuse Dashboard

```bash
# Start Langfuse
docker compose --profile ml up -d langfuse

# Open in browser
open http://localhost:3001
```

**What you'll see:**
- All LLM requests and responses
- Latency and token count
- Errors and exceptions
- Usage analytics

---

## Frequently Asked Questions

### Q: How to add new documents?

```bash
# Simply add PDF to docs/documents/
cp my_document.pdf docs/documents/

# And run ingestion again
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

### Q: How to select another LLM (OpenAI, Groq)?

**Option 1: Via config.py**
```python
API_PROVIDER = 'openai'  # Or 'groq', 'zai'
MODEL_NAME = 'gpt-4-turbo-preview'
```

**Option 2: Via environment variable**
```bash
export API_PROVIDER=groq
python test_api_quick.py
```

### Q: How to improve search quality?

1. **Use DBSF instead of baseline search**
   ```python
   from evaluation.search_engines import DBSFSearchEngine
   engine = DBSFSearchEngine()
   ```

2. **Increase document context**
   ```python
   # In config.py
   CHUNK_SIZE = 1024  # Instead of 512
   ```

3. **Add more documents**
   ```bash
   python ingestion_contextual_kg_fast.py --pdf-path /more/docs
   ```

### Q: How to run on production server?

```bash
# 1. Use production configuration
export ENV=production
export QDRANT_URL=https://qdrant.example.com
export QDRANT_API_KEY=your-secure-key

# 2. Use WSGI server (Gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:application

# 3. Use SSL certificate
# Configure nginx/reverse proxy
```

### Q: How to clear data?

```bash
# Delete Qdrant collection
python -c "
from qdrant_client import QdrantClient
from config import QDRANT_URL, COLLECTION_NAME

client = QdrantClient(QDRANT_URL)
client.delete_collection(COLLECTION_NAME)
"

# Or simply restart Qdrant
docker compose down qdrant
docker compose up -d qdrant
```

---

## Common Errors and Solutions

| Error | Cause | Solution |
|--------|---------|---------|
| `ConnectionError: localhost:6333` | Qdrant not running | `docker compose up -d qdrant` |
| `APIError: invalid_request_error` | Invalid API key | Check `.env` ANTHROPIC_API_KEY |
| `ModuleNotFoundError: qdrant_client` | Dependencies not installed | `pip install -e .` |
| `TimeoutError` during loading | PDF too large | Use `--batch-size 5` |
| Low search metrics | Documents not indexed | Run ingestion again |

---

## Next Steps

1. **Read PROJECT_STRUCTURE.md** - Complete description of all modules
2. **Study ARCHITECTURE.md** - System architecture
3. **Run evaluation/run_ab_test.py** - A/B testing
4. **Try different LLMs** - OpenAI, Groq, Z.AI
5. **Monitor metrics** - MLflow and Langfuse dashboards

---

## Production Readiness Checklist

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

## Useful Commands

```bash
# Project information
python list_available_models.py          # List available models
python check_sparse_vectors.py           # Check sparse vectors

# Testing
python test_api_quick.py                 # Smoke test
python test_api_safe.py                  # Safe test
python evaluation/smoke_test.py          # Full smoke test

# Evaluation
python evaluation/run_ab_test.py         # A/B test with logging
python evaluation/evaluate_with_ragas.py # RAGAS evaluation

# Development
ruff check .                             # Lint check
ruff format .                            # Formatting
mypy . --ignore-missing-imports          # Type checking
python -m pytest tests/                  # Unit tests (if available)
```

---

**Last Updated**: 2024-10-29
**Version**: 2.0.1
**Repository**: https://github.com/yastman/rag
