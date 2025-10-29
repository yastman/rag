# Contextual RAG v2.0.1 Optimization Plan

**Date:** 2025-10-23
**System Version:** v2.0.1
**Status:** Production-ready with ML Platform integration

---

## 📊 Current System State

### Performance (based on A/B test, 150 queries)

| Metric | Baseline (Dense) | DBSF+ColBERT | Change |
|---------|------------------|--------------|--------|
| **Recall@1** | 91.3% | 94.0% | +2.9% ✅ |
| **Recall@10** | 100.0% | 99.3% | -0.7% |
| **NDCG@10** | 96.2% | 97.1% | +1.0% ✅ |
| **MRR** | 94.9% | 96.4% | +1.5% ✅ |
| **Latency** | 0.673s | 0.690s | +2.5% |

**Conclusion:** DBSF+ColBERT shows better quality (+2.9% Recall@1) with minimal speed reduction (+17ms).

### Memory Usage (Docker)

| Service | Used | Limit | % | Status |
|---------|------|-------|---|--------|
| **BGE-M3** | 2.048 GB | 3 GB | 68% | ⚠️ High load |
| **Docling** | 2.786 GB | 11.68 GB | 24% | ✅ Normal |
| **Qdrant** | 233.6 MB | 768 MB | 30% | ✅ Normal |
| **MLflow** | 604.6 MB | 1 GB | 59% | ✅ Normal |
| **Langfuse** | 182.1 MB | 1 GB | 18% | ✅ Normal |

### Storage

- **venv:** 7.8 GB (Python dependencies)
- **Qdrant collections:** 4 collections (uk_civil_code_v2 active: 132 points)
- **Documentation:** 1.1 MB
- **Evaluation:** 1.8 MB

### Dependencies

- **PyMuPDF:** ✅ Used (174 mentions in code)
- **OpenAI SDK:** ✅ Used (246 mentions)
- **Groq SDK:** ✅ Used (15 mentions)
- **Anthropic SDK:** ✅ Used (for context generation)

---

## 🎯 Priority Optimization Areas

### 1. Switch to DBSF+ColBERT (HIGH PRIORITY) ⭐⭐⭐ ✅ COMPLETED

**Problem:** System was using Baseline (dense-only), although DBSF+ColBERT shows +2.9% Recall@1.

**Solution:**
- ✅ Added `DEFAULT_SEARCH_ENGINE = "dbsf_colbert"` in config.py
- ✅ Updated README.md with DBSF+ColBERT recommendation (line 147)
- ✅ Created example_search.py with usage demonstration
- ⏭️ Final A/B test on full collection (optional)

**Achieved Effect:**
- ✅ **Quality:** +2.9% Recall@1 (91.3% → 94.0%)
- ✅ **NDCG@10:** +1.0% (96.2% → 97.1%)
- ⚠️ **Latency:** +17ms (0.673s → 0.690s, acceptable)

**Complexity:** Low (config change)
**Time Spent:** 15 minutes
**ROI:** 🔥 Very high

**Completion Date:** 2025-10-23

---

### 2. BGE-M3 Memory Optimization (MEDIUM PRIORITY) ⭐⭐

**Problem:** BGE-M3 uses 2.048 GB / 3 GB (68% load).

**Solution:**
```python
# Add parameters to config.py for FlagEmbedding
BGE_M3_BATCH_SIZE = 32  # Reduce from 64 (if used)
BGE_M3_MAX_LENGTH = 512  # Limit text length
BGE_M3_NORMALIZE = True  # Normalize vectors for memory savings
```

**Alternative:** Use model quantization (FP16 → INT8).

**Expected Effect:**
- ✅ Memory reduction by 20-30% (to ~1.5 GB)
- ✅ Slight inference speedup (~10-15%)
- ⚠️ Minimal quality reduction (<0.5%)

**Complexity:** Medium
**Time:** 2-3 hours (quality testing)
**ROI:** 🔥 Medium

---

### 3. Cleanup of Unused Qdrant Collections (LOW PRIORITY) ⭐

**Problem:** 4 collections in Qdrant, some may be outdated.

**Solution:**
```bash
# Check collection usage
curl -H "api-key: ..." http://localhost:6333/collections

# Delete unused collections
curl -X DELETE -H "api-key: ..." \
  http://localhost:6333/collections/{collection_name}
```

**Collections to Check:**
- `uk_civil_code_contextual_kg` (may be old version)
- `ukraine_criminal_code_as_of_2010_ru_contextual_kg` (outdated document version)

**Expected Effect:**
- ✅ Free disk space (minor)
- ✅ Simplified management

**Complexity:** Low
**Time:** 15 minutes
**ROI:** Low

---

### 4. Qdrant HNSW Parameters Tuning (MEDIUM PRIORITY) ⭐⭐

**Current Configuration:**
```json
{
  "hnsw_config": {
    "m": 16,
    "ef_construct": 200
  }
}
```

**Problem:** `ef_construct=200` may be excessive for 132 points.

**Solution:**
```python
# In config.py
HNSW_EF_CONSTRUCT = 128  # Lower from 200 for small collections
HNSW_M = 16  # Keep (optimal for dense 1024D)
```

**Expected Effect:**
- ✅ 20-30% faster indexing
- ⚠️ Minimal recall reduction (<0.1% for collections <10K points)

**Complexity:** Low
**Time:** 30 minutes (index recreation)
**ROI:** 🔥 Medium (when scaling collections)

---

### 5. Async Batch Processing for Embedding (HIGH PRIORITY) ⭐⭐⭐

**Current Implementation:** Based on code, `aiohttp` and async are already used.

**Verify:**
- Is batch embedding used for BGE-M3?
- Batch size (optimal 32-64)

**Solution (if not implemented):**
```python
async def embed_batch(texts: list[str], batch_size=32):
    """Batch embedding with memory control"""
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        embeddings = await bge_model.encode_async(batch)
        results.extend(embeddings)
    return results
```

**Expected Effect:**
- ✅ 15-50x faster ingestion (if not implemented)
- ✅ Reduced load on BGE-M3

**Complexity:** Medium (if not implemented)
**Time:** 1-2 hours
**ROI:** 🔥🔥🔥 Very high (if not implemented)

---

### 6. Monitoring and Alerting via MLflow/Langfuse (LOW PRIORITY) ⭐

**Current Status:** MLflow and Langfuse integrated (Phase 3 completed).

**Improvements:**
- Add automatic alerts when Recall@1 drops < 90%
- Configure A/B testing through MLflow Experiments
- Use Langfuse for latency tracking

**Expected Effect:**
- ✅ Early detection of quality degradation
- ✅ Production performance control

**Complexity:** Medium
**Time:** 3-4 hours
**ROI:** 🔥 Medium (long-term benefit)

---

### 7. Caching for Repeated Queries (MEDIUM PRIORITY) ⭐⭐

**Problem:** No embedding caching for frequent queries.

**Solution:**
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def get_cached_embedding(query_hash: str):
    """LRU cache for embedding queries"""
    pass
```

**Alternative:** Use Redis for distributed caching.

**Expected Effect:**
- ✅ 80-90% latency reduction for repeated queries
- ⚠️ ~100-200 MB memory increase (for 1000 queries)

**Complexity:** Medium
**Time:** 2-3 hours
**ROI:** 🔥 High (depends on usage patterns)

---

### 8. Dependencies Optimization (LOW PRIORITY) ⭐

**Problem:** venv takes 7.8 GB.

**Analysis:**
- PyMuPDF, OpenAI, Groq - all used
- MLflow, Langfuse, RAGAS - recently added for ML Platform

**Solution:**
```bash
# Check unused dependencies
pip list --not-required

# Clear caches
pip cache purge  # Frees ~500MB-1GB
```

**Expected Effect:**
- ✅ Free 500MB-1GB disk space
- ⚠️ Minimal benefit (disk not critical)

**Complexity:** Low
**Time:** 30 minutes
**ROI:** Low

---

## 📅 Recommended Implementation Plan

### Phase 1: Quick Wins (1 day)

1. ✅ **Switch to DBSF+ColBERT** (+2.9% Recall@1)
2. ✅ **Verify async batch embedding** (potentially +15-50x ingestion)
3. ✅ **Clean old Qdrant collections**

**Expected Effect:** +2.9% quality, potentially significant ingestion speedup.

---

### Phase 2: Resource Optimization (2-3 days)

4. ⚙️ **Optimize BGE-M3 memory** (reduce by 20-30%)
5. ⚙️ **Configure HNSW ef_construct** (faster indexing)
6. ⚙️ **Add query caching** (80-90% latency reduction for repeats)

**Expected Effect:** Reduced memory, faster indexing, improved UX.

---

### Phase 3: Long-term Improvements (1 week)

7. 📊 **Configure monitoring via MLflow/Langfuse**
8. 🧹 **Clean dependencies and caches**

**Expected Effect:** Quality control, free disk space.

---

## 🎯 Expected Results After Optimization

| Metric | Before | After | Change |
|---------|--------|-------|--------|
| **Recall@1** | 91.3% | 94.0% | +2.9% ✅ |
| **Latency (avg)** | 0.673s | 0.550-0.690s | -18% to +2.5% |
| **BGE-M3 Memory** | 2.048 GB | ~1.5 GB | -27% ✅ |
| **Ingestion Speed** | Baseline | +15-50x | 🔥 (if not async) |
| **Disk Space** | 7.8 GB venv | ~7.0 GB | -10% |

---

## ⚠️ Risks and Limitations

1. **DBSF+ColBERT:** Slight latency increase (+17ms) - acceptable for quality.
2. **BGE-M3 quantization:** May reduce quality by 0.5-1% - requires testing.
3. **HNSW ef_construct:** When scaling >10K points may require increase.

---

## 📝 Next Steps

1. **Immediately:**
   - Switch to DBSF+ColBERT (change config)
   - Verify async batch embedding in code

2. **This Week:**
   - Run A/B test of BGE-M3 with memory optimization
   - Configure HNSW ef_construct for current collection

3. **Next Month:**
   - Implement caching for repeated queries
   - Configure quality monitoring via MLflow

---

**Author:** Claude Code
**Date:** 2025-10-23
**Status:** Ready for implementation ✅
