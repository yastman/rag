# ADR-0004: RedisVL Semantic Cache with RRF Thresholds

**Status:** Accepted

**Date:** 2026-02-10

## Context

We needed a semantic cache that:
- Stores query-response pairs
- Supports semantic similarity matching
- Integrates with existing Redis infrastructure
- Supports per-query-type thresholds

## Decision

Use **RedisVL SemanticCache** for semantic caching, with distance thresholds on **RRF scale** (not cosine similarity).

### Why RedisVL

| Factor | RedisVL | External Services |
|--------|---------|------------------|
| Infrastructure | Existing Redis | Additional service |
| Latency | Local | Network round-trip |
| Cost | Infrastructure only | Per-request pricing |
| Control | Full | Limited |

### Why RRF Scale Thresholds

The cache uses **Reciprocal Rank Fusion** scale for thresholds, not cosine similarity [0-1]:

```
RRF score = 1 / (k + rank), where k = 60
```

- Rank 1: RRF = 1/61 ≈ 0.0164
- Rank 60: RRF = 1/120 ≈ 0.0083
- Rank 140: RRF = 1/200 = 0.005

**Why this matters:**
- `grade_confidence` from grade node is RRF scale
- Cache store threshold must match: `>= 0.005`
- Using cosine thresholds (e.g., 0.8) would result in no stores

## Consequences

### Positive
- Fast semantic cache with Redis
- Query-type-specific thresholds
- No new infrastructure

### Negative
- Threshold tuning required per query type
- RRF scale vs cosine confusion (documentation critical)
- RedisVL import adds ~7.5s to test collection

## Cache Configuration

```python
cache_thresholds = {
    "FAQ": 0.12,        # Most lenient
    "ENTITY": 0.10,
    "GENERAL": 0.08,   # Default
    "STRUCTURED": 0.05, # Strictest
}
```

## References

- Cache implementation: `telegram_bot/integrations/cache.py`
- RRF formula: [CArtE SIGIR 2022](https://arxiv.org/abs/2203.10568)
