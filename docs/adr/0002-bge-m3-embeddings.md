# ADR-0002: BGE-M3 as Primary Embedding Model

**Status:** Accepted

**Date:** 2026-01-20

## Context

We needed an embedding model that supports:
- Dense embeddings for semantic search
- Sparse embeddings for keyword matching
- ColBERT vectors for reranking
- Self-hosted deployment for cost control

## Decision

Use **BGE-M3** (BAAI/bge-m3) as the primary embedding model, self-hosted via Docker.

### Why Self-Hosted

| Factor | API-Based | Self-Hosted |
|--------|-----------|-------------|
| Cost | Per-token pricing | Fixed infrastructure cost |
| Latency | Network round-trip | Local network |
| Privacy | Data leaves infrastructure | Data stays local |
| Control | Limited model options | Full control |

### Why BGE-M3

1. **Multi-vector support** — Dense + Sparse + ColBERT in one model
2. **State-of-the-art** — competitive with proprietary models on MTEB benchmark
3. **Self-hostable** — Available as ONNX or PyTorch model
4. **Russian language support** — Strong performance on multilingual benchmarks

## Consequences

### Positive
- Single model for all embedding needs
- Cost predictable at scale
- Full data privacy
- Low latency (local network)

### Negative
- Infrastructure cost for GPU/CPU resources
- Model updates require redeployment
- Initial setup complexity

## Configuration

```bash
BGE_M3_URL=http://bge-m3:8000  # Container URL
```

## References

- [BGE-M3 Model Card](https://huggingface.co/BAAI/bge-m3)
- [MTEB Benchmark](https://huggingface.co/spaces/mteb/leaderboard)
