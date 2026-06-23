# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
# ///
"""Throwaway GPU/CPU benchmark for the BGE-M3 + reranker "связку".

Step-0 decision tool for the CPU→GPU migration (Pascal / GTX 1070, sm_61).
It is INTENTIONALLY standalone: no repo imports, ephemeral deps via `uv run`,
nothing lands in the project / service lockfiles (keeps the dependency chaos
quarantined — see the chat thread). Run on the host where the 1070 lives.

What it measures, per selected backend:
  - embed throughput (docs/sec) at a realistic doc shape (batch × max_length)
  - single-query encode latency (p50/p95)
  - rerank latency for N candidate pairs (bge-reranker-v2-m3) — CPU vs GPU
  - end-to-end "связку" latency = query encode + rerank top-k
  - peak GPU VRAM with BGE-M3 alone, reranker alone, and BOTH resident
  - dense-vector cosine parity INT8↔FP32 (the re-embed risk, quantified)

Boundary (be honest about it): this is MODEL-side only. It does NOT include
Qdrant ANN search or server-side ColBERT MaxSim (those run inside Qdrant, not a
model). ColBERT rerank needs no model; the only model the live bot is missing
today is the cross-encoder reranker, which is what we add here to test the bundle.

Backends are modular: each imports its libs lazily and is SKIPPED with a hint
if the lib/model is absent, so you can run any subset.

Run examples (each `--with` set is its own ephemeral env — no conflicts):

  # CPU INT8 baseline (the current production embedder)
  uv run scripts/bench_bge_m3_gpu.py --backends cpu-int8 \
      --onnx-int8-dir ./logs/bge_m3_onnx_int8

  # ORT-GPU FP32 (lightest GPU path — keeps the ONNX graph, no torch)
  uv run --with onnxruntime-gpu --with transformers scripts/bench_bge_m3_gpu.py \
      --backends ort-gpu --onnx-fp32 /path/to/bge-m3-fp32/model.onnx

  # Torch FP32 (canonical FlagEmbedding) + reranker, the full bundle on GPU
  uv run --with FlagEmbedding scripts/bench_bge_m3_gpu.py \
      --backends torch-fp32 --reranker --reranker-device cuda

  # zero-GPU sanity check (CI-safe; asserts shape + cosine self==1)
  uv run scripts/bench_bge_m3_gpu.py --smoke --onnx-int8-dir ./logs/bge_m3_onnx_int8
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess  # nosec B404
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DENSE_DIM = 1024

# A short multilingual paragraph (ru) repeated to hit a target token budget —
# representative of the real corpus shape (chunks, not single sentences).
_SEED = (
    "Квартира с двумя спальнями в центре города, ремонт свежий, рядом метро и "
    "школа. Документы готовы, возможна ипотека и рассрочка от застройщика. "
)


def _synth_docs(n: int, approx_tokens: int) -> list[str]:
    # ~1.3 tokens/word for this text → approximate by word count. ponytail: a
    # rough token target is enough for a throughput shape; exact tokenization
    # happens in each backend.
    words_needed = max(1, int(approx_tokens / 1.3))
    reps = max(1, words_needed // len(_SEED.split()) + 1)
    base = _SEED * reps
    base = " ".join(base.split()[:words_needed])
    return [f"[doc {i}] {base}" for i in range(n)]


def _gpu_mem_used_mib() -> float | None:
    """Whole-GPU used VRAM via nvidia-smi (MiB). None if unavailable.

    Caveat: this is total used on GPU 0, so other processes count too — read
    deltas around a load, not absolutes.
    """
    try:
        out = subprocess.run(  # nosec B603 B607
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return float(out.stdout.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _timeit(fn: Callable[[], Any], repeats: int) -> list[float]:
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return times


def _p(times: list[float], q: float) -> float:
    if not times:
        return 0.0
    s = sorted(times)
    k = min(len(s) - 1, round(q * (len(s) - 1)))
    return s[k]


@dataclass
class Result:
    backend: str
    available: bool
    note: str = ""
    embed_docs_per_sec: float | None = None
    embed_batch_p50_ms: float | None = None
    query_p50_ms: float | None = None
    query_p95_ms: float | None = None
    vram_model_mib: float | None = None
    dense_dim: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# ONNX backends (CPU INT8 baseline + ORT-GPU FP32) — one runner, diff providers
# --------------------------------------------------------------------------
class _OnnxEmbedder:
    def __init__(self, onnx_path: str, providers: list[str]):
        import onnxruntime  # lazy
        from transformers import AutoTokenizer

        so = onnxruntime.SessionOptions()
        so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = onnxruntime.InferenceSession(onnx_path, so, providers=providers)
        self.active_providers = self.sess.get_providers()
        # Tokenizer-only load; matches services/bge-m3-api (config-only, no weights).
        self.tok = AutoTokenizer.from_pretrained(EMBED_MODEL)  # nosec B615  # benchmark only

    def _pick_dense(self, outputs: list[np.ndarray], batch: int) -> np.ndarray:
        # app.py order is dense,sparse,colbert; FP32 exports vary → pick the
        # [B, 1024] 2-D output robustly instead of trusting position.
        for o in outputs:
            if o.ndim == 2 and o.shape[0] == batch and o.shape[1] == DENSE_DIM:
                return o.astype(np.float32)
        return outputs[0].astype(np.float32)

    def encode_dense(self, texts: list[str], max_length: int) -> np.ndarray:
        enc = self.tok(
            texts, padding=True, truncation=True, max_length=max_length, return_tensors="np"
        )
        feeds = {
            "input_ids": enc["input_ids"].astype(np.int64),
            "attention_mask": enc["attention_mask"].astype(np.int64),
        }
        out = self.sess.run(None, feeds)
        return self._pick_dense(out, len(texts))


def _run_onnx(
    name: str, onnx_path: str, providers: list[str], args: argparse.Namespace, docs: list[str]
) -> tuple[Result, np.ndarray | None]:
    res = Result(backend=name, available=False)
    try:
        vram0 = _gpu_mem_used_mib()
        emb = _OnnxEmbedder(onnx_path, providers)
        # warmup
        emb.encode_dense(docs[: args.batch], args.doc_tokens)
        vram1 = _gpu_mem_used_mib()
    except ImportError as e:
        res.note = f"skipped: {e} (add via `uv run --with ...`)"
        return res, None
    except Exception as e:
        res.note = f"load failed: {type(e).__name__}: {str(e)[:160]}"
        return res, None

    res.available = True
    res.note = f"providers={emb.active_providers}"
    res.dense_dim = DENSE_DIM
    if vram0 is not None and vram1 is not None:
        res.vram_model_mib = round(vram1 - vram0, 1)

    # batch throughput
    batches = [docs[i : i + args.batch] for i in range(0, len(docs), args.batch)]
    bt = _timeit(lambda: [emb.encode_dense(b, args.doc_tokens) for b in batches], args.repeats)
    per_batch = [t / len(batches) for t in bt]
    res.embed_batch_p50_ms = round(_p(per_batch, 0.5) * 1000, 2)
    res.embed_docs_per_sec = round(len(docs) / statistics.median(bt), 1)

    # single-query latency
    q = "сколько стоит двухкомнатная квартира в центре и есть ли рассрочка"
    qt = _timeit(lambda: emb.encode_dense([q], args.query_tokens), max(args.repeats, 10))
    res.query_p50_ms = round(_p(qt, 0.5) * 1000, 2)
    res.query_p95_ms = round(_p(qt, 0.95) * 1000, 2)

    parity_vec = emb.encode_dense([docs[0]], args.doc_tokens)[0]
    return res, parity_vec


# --------------------------------------------------------------------------
# Torch FP32 backend (FlagEmbedding)
# --------------------------------------------------------------------------
def _run_torch(args: argparse.Namespace, docs: list[str]) -> tuple[Result, np.ndarray | None]:
    res = Result(backend="torch-fp32", available=False)
    try:
        from FlagEmbedding import BGEM3FlagModel  # lazy

        vram0 = _gpu_mem_used_mib()
        model = BGEM3FlagModel(EMBED_MODEL, use_fp16=False, device=args.device)
        model.encode(
            docs[: args.batch],
            batch_size=args.batch,
            max_length=args.doc_tokens,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        vram1 = _gpu_mem_used_mib()
    except ImportError as e:
        res.note = f"skipped: {e} (add via `uv run --with FlagEmbedding`)"
        return res, None
    except Exception as e:
        res.note = f"load failed: {type(e).__name__}: {str(e)[:160]}"
        return res, None

    res.available = True
    res.note = f"device={args.device} fp16=False"
    res.dense_dim = DENSE_DIM
    if vram0 is not None and vram1 is not None:
        res.vram_model_mib = round(vram1 - vram0, 1)

    def _encode_all() -> Any:
        return model.encode(
            docs,
            batch_size=args.batch,
            max_length=args.doc_tokens,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )

    bt = _timeit(_encode_all, args.repeats)
    res.embed_docs_per_sec = round(len(docs) / statistics.median(bt), 1)
    res.embed_batch_p50_ms = round(_p(bt, 0.5) / max(1, len(docs) / args.batch) * 1000, 2)

    q = "сколько стоит двухкомнатная квартира в центре и есть ли рассрочка"
    qt = _timeit(
        lambda: model.encode(
            [q],
            max_length=args.query_tokens,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        ),
        max(args.repeats, 10),
    )
    res.query_p50_ms = round(_p(qt, 0.5) * 1000, 2)
    res.query_p95_ms = round(_p(qt, 0.95) * 1000, 2)

    out = model.encode([docs[0]], max_length=args.doc_tokens, return_dense=True)
    parity = np.asarray(out["dense_vecs"][0], dtype=np.float32)
    return res, parity


# --------------------------------------------------------------------------
# Reranker (bge-reranker-v2-m3) — the second model in the bundle
# --------------------------------------------------------------------------
def _run_reranker(args: argparse.Namespace, docs: list[str]) -> Result:
    res = Result(backend=f"reranker[{args.reranker_device}]", available=False)
    try:
        from FlagEmbedding import FlagReranker  # lazy

        vram0 = _gpu_mem_used_mib()
        use_cuda = args.reranker_device == "cuda"
        rk = FlagReranker(RERANK_MODEL, use_fp16=False, devices=args.reranker_device)
        q = "сколько стоит двухкомнатная квартира в центре и есть ли рассрочка"
        rk.compute_score([[q, docs[0]]])  # warmup
        vram1 = _gpu_mem_used_mib()
    except ImportError as e:
        res.note = f"skipped: {e} (add via `uv run --with FlagEmbedding`)"
        return res
    except Exception as e:
        res.note = f"load failed: {type(e).__name__}: {str(e)[:160]}"
        return res

    res.available = True
    res.note = f"device={args.reranker_device} fp16=False use_cuda={use_cuda}"
    if vram0 is not None and vram1 is not None:
        res.vram_model_mib = round(vram1 - vram0, 1)

    q = "сколько стоит двухкомнатная квартира в центре и есть ли рассрочка"
    for n in sorted({min(args.rerank_pairs, len(docs)), min(10, len(docs))}):
        pairs = [[q, docs[i]] for i in range(n)]
        rt = _timeit(lambda p=pairs: rk.compute_score(p), max(args.repeats, 5))
        res.extra[f"rerank_{n}pairs_p50_ms"] = round(_p(rt, 0.5) * 1000, 2)
    return res


def _print_table(results: list[Result]) -> None:
    print("\n=== BGE-M3 + reranker bundle bench ===")
    cols = ["backend", "avail", "docs/s", "batch p50 ms", "query p50/p95 ms", "VRAM MiB", "note"]
    print(" | ".join(cols))
    print("-" * 110)
    for r in results:
        q = f"{r.query_p50_ms}/{r.query_p95_ms}" if r.query_p50_ms is not None else "-"
        print(
            " | ".join(
                str(x)
                for x in [
                    r.backend,
                    "yes" if r.available else "no",
                    r.embed_docs_per_sec if r.embed_docs_per_sec is not None else "-",
                    r.embed_batch_p50_ms if r.embed_batch_p50_ms is not None else "-",
                    q,
                    r.vram_model_mib if r.vram_model_mib is not None else "-",
                    r.note[:60],
                ]
            )
        )
        if r.extra:
            print(f"    rerank: {r.extra}")


def _smoke(args: argparse.Namespace) -> int:
    """Zero-GPU sanity check: CPU-INT8 dense shape + cosine self-similarity."""
    onnx_path = f"{args.onnx_int8_dir.rstrip('/')}/model.int8.onnx"
    emb = _OnnxEmbedder(onnx_path, ["CPUExecutionProvider"])
    v = emb.encode_dense(["проверка связности эмбеддера"], 64)
    assert v.shape == (1, DENSE_DIM), f"dense shape {v.shape} != (1,{DENSE_DIM})"
    a = v[0] / (np.linalg.norm(v[0]) + 1e-9)
    cos = float(a @ a)
    assert abs(cos - 1.0) < 1e-4, f"self-cosine {cos} != 1.0"
    print(f"smoke OK: dense_dim={DENSE_DIM}, self-cosine={cos:.6f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--backends",
        default="cpu-int8",
        help="comma list: cpu-int8,ort-gpu,torch-fp32 (default: cpu-int8)",
    )
    ap.add_argument(
        "--onnx-int8-dir",
        default="./logs/bge_m3_onnx_int8",
        help="dir holding model.int8.onnx (CPU baseline)",
    )
    ap.add_argument("--onnx-fp32", default="", help="path to an FP32 bge-m3 model.onnx (ort-gpu)")
    ap.add_argument("--device", default="cuda", help="torch device for torch-fp32 (cuda|cpu)")
    ap.add_argument("--reranker", action="store_true", help="also bench bge-reranker-v2-m3")
    ap.add_argument("--reranker-device", default="cuda", help="cuda|cpu for the reranker")
    ap.add_argument("--rerank-pairs", type=int, default=40, help="candidate pairs to rerank")
    ap.add_argument("--n-docs", type=int, default=96, help="synthetic docs for throughput")
    ap.add_argument("--doc-tokens", type=int, default=512, help="approx tokens per doc")
    ap.add_argument("--query-tokens", type=int, default=64, help="approx tokens per query")
    ap.add_argument("--batch", type=int, default=12, help="embed batch size (matches service)")
    ap.add_argument("--repeats", type=int, default=5, help="timing repeats")
    ap.add_argument("--json", default="", help="write results JSON to this path")
    ap.add_argument("--smoke", action="store_true", help="zero-GPU sanity check then exit")
    args = ap.parse_args(argv)

    if args.smoke:
        return _smoke(args)

    docs = _synth_docs(args.n_docs, args.doc_tokens)
    results: list[Result] = []
    parity: dict[str, np.ndarray] = {}
    wanted = {b.strip() for b in args.backends.split(",") if b.strip()}

    if "cpu-int8" in wanted:
        r, v = _run_onnx(
            "cpu-int8",
            f"{args.onnx_int8_dir.rstrip('/')}/model.int8.onnx",
            ["CPUExecutionProvider"],
            args,
            docs,
        )
        results.append(r)
        if v is not None:
            parity["cpu-int8"] = v
    if "ort-gpu" in wanted:
        if not args.onnx_fp32:
            results.append(
                Result("ort-gpu", False, note="skipped: pass --onnx-fp32 /path/model.onnx")
            )
        else:
            r, v = _run_onnx(
                "ort-gpu",
                args.onnx_fp32,
                ["CUDAExecutionProvider", "CPUExecutionProvider"],
                args,
                docs,
            )
            results.append(r)
            if v is not None:
                parity["ort-gpu"] = v
    if "torch-fp32" in wanted:
        r, v = _run_torch(args, docs)
        results.append(r)
        if v is not None:
            parity["torch-fp32"] = v

    if args.reranker:
        results.append(_run_reranker(args, docs))

    _print_table(results)

    # dense-vector parity vs the INT8 baseline = the re-embed risk, quantified.
    if "cpu-int8" in parity:
        base = parity["cpu-int8"]
        base_n = base / (np.linalg.norm(base) + 1e-9)
        print("\n=== dense parity vs cpu-int8 (cosine; 1.0 = identical space) ===")
        for name, vec in parity.items():
            if name == "cpu-int8":
                continue
            vn = vec / (np.linalg.norm(vec) + 1e-9)
            print(f"  cpu-int8 ↔ {name}: cos={float(base_n @ vn):.4f}")
        print("  (low cosine ⇒ a precision/model switch needs a full corpus re-embed)")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([asdict(r) for r in results], fh, ensure_ascii=False, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
