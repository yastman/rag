# Setup Guide - Contextual RAG Pipeline

**Version:** 2.0.1 | **Last Updated:** 2025-10-23

Complete step-by-step installation and configuration guide.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Steps](#installation-steps)
3. [Configuration](#configuration)
4. [Verification](#verification)
5. [First Test Run](#first-test-run)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

**Minimum:**
- Operating System: Linux (Ubuntu 20.04+) or macOS
- Python: 3.9 or higher
- RAM: 4GB available
- Disk: 20GB free space
- Internet connection (for model downloads)

**Recommended for production:**
- Python: 3.10+
- RAM: 8GB+
- Disk: 50GB+ (SSD)
- CPU: 8 cores+

### Required Services

The following services must be running (usually via Docker):

1. **Qdrant** (v1.15.5+)
   - Port: 6333
   - Purpose: Vector database
   - Docker service: `qdrant`

2. **BGE-M3 API** (localhost)
   - Port: 8001
   - Purpose: Text embedding
   - Docker service: `bge-m3-api`

3. **Docling API** (localhost)
   - Port: 5001
   - Purpose: PDF processing (OCR, tables)
   - Docker service: `docling-api`

### API Keys

You need **at least one** of the following API keys for contextualization:

| Provider | Required | Cost | Sign Up |
|----------|----------|------|---------|
| Z.AI | ✅ Recommended | $3/month | https://z.ai |
| Groq | Optional | Free (with limits) | https://groq.com |
| OpenAI | Optional | Pay-per-use (~$8/132 chunks) | https://openai.com |
| Anthropic | Optional | Pay-per-use (~$12/132 chunks) | https://anthropic.com |

---

## Installation Steps

### Step 1: Clone or Navigate to Project

```bash
# If you don't have the project yet
git clone <repository-url>
cd contextual_rag

# Or if already cloned
cd /path/to/contextual_rag
```

### Step 2: Create Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

### Step 3: Install Python Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install all required packages
pip install \
    pymupdf \
    anthropic \
    openai \
    groq \
    python-dotenv \
    numpy \
    aiohttp \
    requests \
    pandas \
    FlagEmbedding \
    scipy

# Or if there's a requirements.txt
pip install -r requirements.txt
```

**Package explanations:**
- `pymupdf` - PDF processing (PyMuPDF)
- `anthropic`, `openai`, `groq` - LLM APIs for contextualization
- `python-dotenv` - Environment variables management
- `numpy`, `scipy`, `pandas` - Data processing
- `aiohttp`, `requests` - HTTP clients (async & sync)
- `FlagEmbedding` - BGE-M3 model utilities

### Step 4: Install Development Tools (Optional)

```bash
# Code quality tools
pip install ruff pre-commit

# Setup pre-commit hooks
pre-commit install
```

This installs:
- `ruff` - Modern Python linter + formatter
- `pre-commit` - Git hooks for code quality

---

## Configuration

### Step 1: Create .env File

```bash
# Copy example file (if exists)
cp .env.example .env

# Or create new file
nano .env
```

### Step 2: Configure .env File

Add the following variables:

```bash
# =============================================================================
# QDRANT CONFIGURATION
# =============================================================================
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_qdrant_api_key_here

# =============================================================================
# EMBEDDING API (BGE-M3)
# =============================================================================
BGE_M3_URL=http://localhost:8001
BGE_M3_TIMEOUT=180

# =============================================================================
# DOCUMENT PROCESSING API
# =============================================================================
DOCLING_URL=http://localhost:5001
DOCLING_TIMEOUT=600

# =============================================================================
# LLM API KEYS (Choose at least ONE)
# =============================================================================

# Z.AI (Recommended - $3/month, unlimited)
ZAI_API_KEY=your_zai_api_key_here

***REMOVED*** (Free tier with rate limits)
#GROQ_API_KEY=your_groq_api_key_here

# OpenAI (Pay-per-use, ~$8 for 132 chunks)
#OPENAI_API_KEY=sk-proj-...

***REMOVED*** Claude (Pay-per-use, ~$12 for 132 chunks)
#ANTHROPIC_API_KEY=sk-ant-...

# =============================================================================
# COLLECTION NAMES (Optional - uses defaults if not set)
# =============================================================================
COLLECTION_BASELINE=uk_civil_code_v2
COLLECTION_CONTEXTUAL_KG=uk_civil_code_contextual_kg

# =============================================================================
# RATE LIMITING (Optional)
# =============================================================================
# Z.AI rate limit delay (seconds between requests)
ZAI_RATE_LIMIT_DELAY=0.1

# Maximum concurrent API calls
ASYNC_SEMAPHORE_LIMIT=10

# =============================================================================
# PDF PATH (Optional)
# =============================================================================
PDF_PATH=/path/to/your/document.pdf
```

### Step 3: Get API Keys

#### Z.AI (Recommended)

1. Go to https://z.ai
2. Sign up for account
3. Subscribe to plan ($3/month)
4. Copy API key from dashboard
5. Paste into `.env` file

###***REMOVED*** (Free Alternative)

1. Go to https://console.groq.com
2. Create account
3. Navigate to API Keys section
4. Create new API key
5. Paste into `.env` file

#### OpenAI (Optional)

1. Go to https://platform.openai.com
2. Create account
3. Add payment method
4. Create API key
5. Paste into `.env` file

###***REMOVED*** (Optional)

1. Go to https://console.anthropic.com
2. Create account
3. Add payment method
4. Create API key
5. Paste into `.env` file

---

## Verification

### Step 1: Verify Docker Services

```bash
# Check all services are running
docker compose ps

# Expected output:
# NAME                    STATUS
# qdrant                  Up (healthy)
# bge-m3-api              Up
# docling-api             Up
```

### Step 2: Test Qdrant Connection

```bash
# Test Qdrant API
curl -H "api-key: YOUR_QDRANT_API_KEY" http://localhost:6333/collections

# Expected: JSON list of collections or empty array []
```

### Step 3: Test BGE-M3 API

```bash
# Check health
curl http://localhost:8001/health

# Expected: {"status":"ok","model_loaded":true}

# Test embedding
curl -X POST http://localhost:8001/encode/dense \
  -H "Content-Type: application/json" \
  -d '{"texts":["test"],"batch_size":1}'

# Expected: JSON with dense_vecs and processing_time
```

### Step 4: Test Docling API

```bash
# Check health
curl http://localhost:5001/health

# Expected: {"status":"healthy"} or similar
```

### Step 5: Verify Python Environment

```bash
# Check Python version
python --version
# Expected: Python 3.9.x or higher

# Verify packages installed
pip list | grep -E "pymupdf|anthropic|openai|groq|FlagEmbedding"

# Expected: All packages listed
```

### Step 6: Test Configuration Loading

```bash
# Run Python and test imports
python -c "
from dotenv import load_dotenv
load_dotenv()
import os

# Check critical variables
assert os.getenv('QDRANT_URL'), 'QDRANT_URL not set'
assert os.getenv('QDRANT_API_KEY'), 'QDRANT_API_KEY not set'
assert os.getenv('BGE_M3_URL'), 'BGE_M3_URL not set'

# Check at least one LLM API key
apis = ['ZAI_API_KEY', 'GROQ_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']
has_api = any(os.getenv(api) for api in apis)
assert has_api, 'No LLM API key configured'

print('✅ Configuration loaded successfully!')
"
```

### Step 7: Validate Configuration

```bash
# Run config validation
python -c "from config import validate_config; validate_config()"

# Expected: No errors, returns True
```

---

## First Test Run

### Quick Test (5 chunks, ~30 seconds)

This tests the complete pipeline with minimal data.

```bash
# Run test mode (processes only 5 chunks)
python ingestion_contextual_kg_fast.py --test

# Expected output:
# ✅ Complexity check complete (~0.3s)
# ✅ Chunking complete (~2s)
# ✅ Contextualization complete (~15-30s)
# ✅ Embedding complete (~5s)
# ✅ Qdrant upsert complete (~2s)
# Total: ~30-45 seconds
```

**What this tests:**
- PDF complexity detection
- Chunking (Docling or PyMuPDF)
- LLM API connectivity
- Contextualization process
- BGE-M3 embedding
- Qdrant upsert

**Expected cost:** $0.01-0.05 (or free with Z.AI/Groq)

### Verify Test Results

```bash
# Check if points were created in Qdrant
curl -H "api-key: YOUR_QDRANT_API_KEY" \
  http://localhost:6333/collections/uk_civil_code_contextual_kg

# Expected: Collection info with points_count: 5
```

### Full Run (All Chunks, 3-6 minutes)

After test succeeds, run full ingestion:

```bash
# Process entire document (132 chunks)
python ingestion_contextual_kg_fast.py

# Expected output:
# Processing 132 chunks...
# Progress: [█████████████████████] 100%
# Total time: 3-6 minutes (depending on API)
# Cost: $0 (Z.AI), ~$8 (OpenAI), ~$12 (Claude)
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError"

**Problem:** Python package not installed

**Solution:**
```bash
# Activate virtual environment
source .venv/bin/activate

# Install missing package
pip install <package-name>

# Or reinstall all
pip install -r requirements.txt
```

### Issue: "Connection refused" (Qdrant/BGE-M3/Docling)

**Problem:** Docker service not running

**Solution:**
```bash
# Check service status
docker compose ps

# Restart service
docker compose restart qdrant
docker compose restart bge-m3-api
docker compose restart docling-api

# Or restart all
docker compose restart
```

### Issue: "API key not found" or "401 Unauthorized"

**Problem:** LLM API key not configured or invalid

**Solution:**
1. Check `.env` file exists in project root
2. Verify API key is correctly pasted (no extra spaces)
3. Test API key directly:

```bash
# Z.AI
curl https://api.z.ai/v1/health -H "Authorization: Bearer YOUR_API_KEY"

***REMOVED***
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer YOUR_API_KEY"

# OpenAI
curl https://api.openai.com/v1/models -H "Authorization: Bearer YOUR_API_KEY"
```

### Issue: "ANTHROPIC_API_KEY not found"

**Problem:** Using wrong API provider module

**Solution:**
The default `ingestion_contextual_kg_fast.py` uses Z.AI. To use other providers:

```bash
# Edit the file and change import:
# from contextualize_zai_async import ContextualRetrievalZAIAsync
# to:
# from contextualize_openai_async import ContextualRetrievalOpenAIAsync
# or:
# from contextualize_groq_async import ContextualRetrievalGroqAsync
```

### Issue: "BGE-M3 model not found"

**Problem:** Model not downloaded or wrong volume path

**Solution:**
```bash
# Check model in volume
docker run --rm -v ai-bge-m3-models:/models alpine ls -lh /models/huggingface/hub/

# If empty, model will download on first API call (~7.7GB, 5-10 min)

# Restart BGE-M3 API to trigger download
docker compose restart bge-m3-api

# Watch logs
docker compose logs -f bge-m3-api
```

### Issue: Rate Limits (Groq/OpenAI Free Tier)

**Problem:** Too many concurrent requests

**Solution:**
Edit `config.py`:

```python
# Reduce concurrent requests
ASYNC_SEMAPHORE_LIMIT = 5  # Default: 10

# Increase delay between requests
ZAI_RATE_LIMIT_DELAY = 0.5  # Default: 0.1
```

### Issue: "Score threshold too high, no results"

**Problem:** Search returns empty results

**Solution:**
Edit `config.py`:

```python
# Lower score thresholds
SCORE_THRESHOLD_DENSE = 0.3      # Default: 0.5
SCORE_THRESHOLD_HYBRID = 0.2     # Default: 0.3
SCORE_THRESHOLD_COLBERT = 0.25   # Default: 0.4
```

### Issue: Code Quality Errors

**Problem:** Ruff reports code quality issues

**Solution:**
```bash
# Auto-fix most issues
ruff check --fix .

# Format code
ruff format .

# Check remaining issues
ruff check .
```

### Getting Help

If issues persist:

1. **Check logs:**
   ```bash
   # Python script logs
   python ingestion_contextual_kg_fast.py 2>&1 | tee log.txt

   # Docker service logs
   docker compose logs qdrant
   docker compose logs bge-m3-api
   docker compose logs docling-api
   ```

2. **Verify system status:**
   ```bash
   # Run all verification steps
   ./scripts/verify_setup.sh  # If script exists
   ```

3. **Review documentation:**
   - [README.md](README.md) - Overview
   - [ARCHITECTURE.md](ARCHITECTURE.md) - System details
   - [CODE_QUALITY.md](CODE_QUALITY.md) - Code standards

4. **Check external services:**
   - Z.AI status: https://status.z.ai
   - Groq status: https://status.groq.com
   - OpenAI status: https://status.openai.com

---

## Next Steps

After successful setup:

1. **Run Evaluation:**
   ```bash
   cd evaluation
   python run_ab_test.py
   ```

2. **Explore Search Engines:**
   - Test baseline search
   - Test hybrid RRF search
   - Implement DBSF + ColBERT search

3. **Customize Configuration:**
   - Adjust score thresholds
   - Tune HNSW parameters
   - Optimize batch sizes

4. **Create Payload Indexes:**
   ```bash
   python create_payload_indexes.py
   ```

5. **Review Code Quality:**
   - Read [CODE_QUALITY.md](CODE_QUALITY.md)
   - Setup pre-commit hooks
   - Configure IDE integration

---

## Production Checklist

Before deploying to production:

- [ ] All Docker services running and healthy
- [ ] API keys configured and tested
- [ ] Python dependencies installed
- [ ] Configuration validated (`validate_config()` passes)
- [ ] Test run successful (5 chunks)
- [ ] Full ingestion tested (if applicable)
- [ ] Search working correctly
- [ ] Evaluation metrics acceptable
- [ ] Code quality checks passing (`ruff check .`)
- [ ] Backup/restore procedures tested
- [ ] Monitoring/logging configured
- [ ] Documentation reviewed

---

## Related Documentation

- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [CODE_QUALITY.md](CODE_QUALITY.md) - Code quality standards

---

**Last Updated:** 2025-10-23
**Need Help?** Check troubleshooting section or review architecture documentation.
