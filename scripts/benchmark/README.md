# scripts/benchmark/

A/B comparison and search quality benchmarks for the RAG pipeline.

These scripts measure retrieval quality, latency, and precision across
different embedding and quantization strategies. They are **not** pytest
tests and are not collected by the test runner.

## Contents

| Script | Purpose |
|--------|---------|
| `contextualized_ab.py` | Voyage contextualized vs baseline embeddings A/B |
| `quantization_ab.py` | Binary quantization vs unquantized A/B |
| `quantization_int8_vs_binary.py` | INT8 scalar vs binary quantization comparison |
| `search_quality.py` | End-to-end search quality evaluation |

## Running

```bash
python scripts/benchmark/contextualized_ab.py
python scripts/benchmark/quantization_ab.py --k 5 --runs 3
python scripts/benchmark/quantization_int8_vs_binary.py --base contextual_bulgaria_voyage
python scripts/benchmark/search_quality.py
```
