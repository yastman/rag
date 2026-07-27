from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


MODEL_ID = "BAAI/bge-m3"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
MODEL_ARTIFACTS = {
    "pytorch_model.bin": "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38",
    "colbert_linear.pt": "19bfbae397c2b7524158c919d0e9b19393c5639d098f0a66932c91ed8f5f9abb",
    "sparse_linear.pt": "45c93804d2142b8f6d7ec6914ae23a1eee9c6a1d27d83d908a20d2afb3595ad9",
    "tokenizer.json": "21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08",
}
MODEL_FILES = [
    *MODEL_ARTIFACTS,
    "config.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
]


class EncodeRequest(BaseModel):
    texts: Annotated[list[str], Field(min_length=1, max_length=64)]


class SparseVector(BaseModel):
    indices: list[int]
    values: list[float]


class HybridResponse(BaseModel):
    dense_vecs: list[list[float]]
    sparse_vecs: list[SparseVector]


def verified_model_path() -> str:
    from huggingface_hub import snapshot_download

    path = Path(
        snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            allow_patterns=MODEL_FILES,
        )
    )
    for name, expected_hash in MODEL_ARTIFACTS.items():
        actual_hash = hashlib.file_digest((path / name).open("rb"), "sha256").hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"BGE-M3 artifact hash mismatch: {name}")
    return str(path)


@lru_cache(maxsize=1)
def model() -> Any:
    from FlagEmbedding import BGEM3FlagModel

    return BGEM3FlagModel(verified_model_path(), use_fp16=False)


def sparse_vector(weights: dict[str, float]) -> SparseVector:
    indices: list[int] = []
    values: list[float] = []
    for token_id, weight in weights.items():
        index = int(token_id)
        value = float(weight)
        if index < 0 or value < 0 or not math.isfinite(value):
            raise ValueError("BGE-M3 emitted an invalid sparse weight")
        indices.append(index)
        values.append(value)
    return SparseVector(indices=indices, values=values)


app = FastAPI(title="BGE-M3 hybrid encoder", version="2")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/encode/hybrid", response_model=HybridResponse)
def encode_hybrid(request: EncodeRequest) -> HybridResponse:
    try:
        encoded = model().encode(
            request.texts,
            batch_size=len(request.texts),
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense = encoded["dense_vecs"]
        sparse = [sparse_vector(weights) for weights in encoded["lexical_weights"]]
        if len(dense) != len(request.texts) or len(sparse) != len(request.texts):
            raise ValueError("BGE-M3 output cardinality does not match the request")
        if any(len(vector) != 1024 for vector in dense):
            raise ValueError("BGE-M3 dense vector dimension is not 1024")
        return HybridResponse(dense_vecs=dense, sparse_vecs=sparse)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
