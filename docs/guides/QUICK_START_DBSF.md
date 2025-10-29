# Quick Start: DBSF + ColBERT Search

**TL;DR:** Run 3 commands to evaluate DBSF+ColBERT vs Baseline.

---

## 3-Minute Quick Start

```bash
# 1. Create payload indexes (one-time setup, ~30 seconds)
cd /srv/contextual_rag
python create_payload_indexes.py

# 2. Run A/B test (depends on query count, ~5-10 minutes)
cd evaluation
python run_ab_test.py

# 3. View results
cat reports/AB_TEST_REPORT_*.md | tail -50
```

---

## What to Look For in Results

### Success Criteria

**DBSF+ColBERT wins** if:
- Recall@10 > 70% (baseline: 65%)
- Improvement over baseline > +10%
- NDCG@10 > 0.65 (baseline: 0.577)

**Investigate** if:
- Recall@10 < 65% (worse than baseline)
- Failure rate > 20%
- Search time > 2x baseline

### Example Good Result

```
## Executive Summary

| Metric | Baseline | DBSF+ColBERT | Best |
|--------|----------|--------------|------|
| Recall@10 | 0.6500 | 0.7800 | DBSF |  ← +20% improvement
| NDCG@10 | 0.5768 | 0.6891 | DBSF |   ← +19.5% improvement
| MRR | 0.4231 | 0.5467 | DBSF |       ← +29.2% improvement
```

---

## Configuration Tuning

### If Recall@10 is Too Low (< 70%)

**Option 1: Lower score threshold**
```python
# In config.py
SCORE_THRESHOLD_HYBRID = 0.2  # Was 0.3
```

**Option 2: Increase stage 1 candidates**
```python
# In config.py
RETRIEVAL_LIMIT_STAGE1 = 200  # Was 100
```

**Option 3: Higher HNSW precision**
```python
# In config.py
HNSW_EF_HIGH_PRECISION = 512  # Was 256
```

### If Search is Too Slow (> 2s per query)

**Option 1: Lower HNSW ef**
```python
# In config.py
HNSW_EF_HIGH_PRECISION = 128  # Was 256
```

**Option 2: Reduce stage 1 candidates**
```python
# In config.py
RETRIEVAL_LIMIT_STAGE1 = 50  # Was 100
```

**Option 3: Use only minimal payload fields**
```python
# Already configured in search_engines.py
self.payload_fields = PAYLOAD_FIELDS_MINIMAL  # ["article_number", "text"]
```

---

## Testing Individual Components

### Test 1: Verify Payload Indexes

```bash
python create_payload_indexes.py --verify-only

# Expected output:
# Existing Payload Indexes:
#   ✓ article_number: integer
#   ✓ chapter_number: integer
#   ✓ section_number: integer
#   ✓ book_number: integer
```

### Test 2: Quick Search Test

```python
from FlagEmbedding import BGEM3FlagModel
from evaluation.search_engines import create_search_engine

# Load model
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

# Create DBSF+ColBERT engine
engine = create_search_engine(
    "dbsf_colbert",
    "ukraine_criminal_code_zai_full",
    model
)

# Test search
results = engine.search("кража имущества", top_k=5)

# Print results
for i, r in enumerate(results, 1):
    print(f"{i}. Article {r['article_number']}: {r['score']:.4f}")
```

Expected output:
```
1. Article 185: 0.8234
2. Article 187: 0.7891
3. Article 186: 0.7456
...
```

### Test 3: Compare All 3 Engines

```python
baseline = create_search_engine("baseline", "ukraine_criminal_code_zai_full", model)
hybrid = create_search_engine("hybrid", "ukraine_criminal_code_zai_full", model)
dbsf = create_search_engine("dbsf_colbert", "ukraine_criminal_code_zai_full", model)

query = "крадіжка майна"

print("Baseline results:", [r['article_number'] for r in baseline.search(query, 5)])
print("Hybrid results:", [r['article_number'] for r in hybrid.search(query, 5)])
print("DBSF+ColBERT results:", [r['article_number'] for r in dbsf.search(query, 5)])
```

---

## Common Issues & Fixes

### Issue 1: "No such vector named 'colbert'"

**Cause:** Collection doesn't have ColBERT multivector.

**Fix:**
```bash
cd /srv/contextual_rag
python create_collection_enhanced.py
python ingestion_contextual_kg_fast.py  # Re-ingest data
```

### Issue 2: DBSF search returns empty results

**Cause:** Score threshold too high.

**Quick test:**
```python
engine.score_threshold = 0.0  # Disable threshold
results = engine.search(query, top_k=10)
```

If this works, lower threshold in config.py from 0.3 → 0.2.

### Issue 3: Slow performance (> 5s per query)

**Cause:** HNSW ef too high or ColBERT vectors not optimized.

**Check HNSW config:**
```bash
curl http://localhost:6333/collections/ukraine_criminal_code_zai_full | \
  jq '.result.config.params.vectors.colbert.hnsw_config'
```

**Expected:** `{"m": 0}` (HNSW disabled)

**If not:** Recreate collection with updated schema.

---

## Next Steps After Successful Test

### If DBSF+ColBERT Wins (Recall@10 > 70%)

**Recommend for production:**

1. Update production collection schema:
   ```bash
   python create_collection_enhanced.py
   ```

2. Create payload indexes:
   ```bash
   python create_payload_indexes.py
   ```

3. Update application to use DBSF+ColBERT engine:
   ```python
   engine = create_search_engine("dbsf_colbert", collection, model)
   ```

4. Monitor in production:
   - Track Recall@10, NDCG@10, latency
   - Set alerts for degradation

### If Results Are Close (65-70%)

**Tune parameters:**

1. Try different configurations (see "Configuration Tuning" above)
2. Run A/B test on larger dataset (50+ queries)
3. Analyze per-query-type performance
4. Consider hybrid approach (DBSF for complex queries, baseline for simple)

### If Baseline Still Wins (< 65%)

**Investigate issues:**

1. Check ColBERT vectors are correctly indexed:
   ```bash
   curl http://localhost:6333/collections/ukraine_criminal_code_zai_full | \
     jq '.result.config.params.vectors.colbert'
   ```

2. Verify DBSF fusion is working (check search payload logs)

3. Test with very low threshold (0.1) to rule out filtering issues

4. Compare dense-only vs DBSF fusion vs DBSF+ColBERT separately

---

## Additional Resources

- **Full Implementation Details:** `DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md`
- **Original README:** `README.md`
- **Qdrant DBSF Docs:** https://qdrant.tech/articles/hybrid-search/
- **ColBERT Docs:** https://qdrant.tech/documentation/concepts/hybrid-queries/

---

**Questions or Issues?**
- Check implementation summary for detailed troubleshooting
- Review official Qdrant documentation
- Verify all prerequisites (Qdrant 1.11+, BGE-M3 model, correct collection schema)

**Ready to run?**
```bash
cd /srv/app/evaluation
python run_ab_test.py
```

**Estimated time:** 5-10 minutes for full evaluation.
