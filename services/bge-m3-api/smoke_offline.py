"""Offline container smoke for the pinned BGE-M3 artifact (#3366).

Runs INSIDE the built image with ``--network none``: starts the real app
server (its lifespan verifies and loads the pinned artifact), then exercises
``/health`` and the hybrid encode endpoint with Russian, Bulgarian, and
English fixtures, asserting the dense/sparse/ColBERT dimensions and
cardinalities consumed by the application.

Exit code 0 with ``OFFLINE SMOKE PASS`` proves the artifact loads and serves
every vector family with no network access and no warm host cache.
"""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time

import uvicorn
from app import app


DENSE_DIM = 1024
COLBERT_DIM = 1024
PORT = 8000
STARTUP_TIMEOUT_S = 300.0

FIXTURES = [
    "Привет, мир! Это тестовое предложение для гибридного поиска по квартире.",
    "Здравей, святко! Това е тестово изречение за хибридно търсене.",
    "Hello world! This is a test sentence for hybrid apartment search.",
]


def _request(conn: http.client.HTTPConnection, method: str, path: str, body: dict | None = None):
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    return response.status, json.loads(raw) if raw else {}


def _fail(message: str) -> None:
    print(f"OFFLINE SMOKE FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    health: dict | None = None
    while health is None:
        try:
            conn.request("GET", "/health")
            response = conn.getresponse()
            body = response.read().decode("utf-8")
            if response.status == 200:
                health = json.loads(body)
        except OSError:
            pass
        if health is None and time.monotonic() > deadline:
            _fail("server did not become healthy before timeout (artifact load failed?)")
        if health is None:
            time.sleep(1.0)

    if not health.get("model_loaded"):
        _fail(f"model not loaded: {health}")
    if not health.get("warmed_up"):
        _fail(f"startup warmup did not complete: {health}")

    status, data = _request(conn, "POST", "/encode/hybrid", {"texts": FIXTURES})
    if status != 200:
        _fail(f"/encode/hybrid returned {status}: {data}")

    dense = data.get("dense_vecs")
    if not isinstance(dense, list) or len(dense) != len(FIXTURES):
        _fail(f"dense_vecs cardinality {dense and len(dense)} != {len(FIXTURES)}")
    for i, row in enumerate(dense):
        if len(row) != DENSE_DIM:
            _fail(f"dense_vecs[{i}] dim {len(row)} != {DENSE_DIM}")
        if all(v == 0.0 for v in row):
            _fail(f"dense_vecs[{i}] is an all-zero vector")

    sparse = data.get("lexical_weights")
    if not isinstance(sparse, list) or len(sparse) != len(FIXTURES):
        _fail("lexical_weights cardinality mismatch")
    for i, item in enumerate(sparse):
        indices, values = item.get("indices"), item.get("values")
        if not indices or not values or len(indices) != len(values):
            _fail(f"lexical_weights[{i}] empty or cardinality mismatch: {item}")
        if any(not isinstance(idx, int) or idx < 0 for idx in indices):
            _fail(f"lexical_weights[{i}] has invalid token indices")
        if any(v <= 0 for v in values):
            _fail(f"lexical_weights[{i}] has non-positive weights")

    colbert = data.get("colbert_vecs")
    if not isinstance(colbert, list) or len(colbert) != len(FIXTURES):
        _fail("colbert_vecs cardinality mismatch")
    for i, token_vectors in enumerate(colbert):
        if not token_vectors or not isinstance(token_vectors, list):
            _fail(f"colbert_vecs[{i}] has no token vectors")
        for j, row in enumerate(token_vectors):
            if len(row) != COLBERT_DIM:
                _fail(f"colbert_vecs[{i}][{j}] dim {len(row)} != {COLBERT_DIM}")
            if all(v == 0.0 for v in row):
                _fail(f"colbert_vecs[{i}][{j}] is an all-zero vector")

    if data.get("partial_failures"):
        _fail(f"unexpected partial failures: {data['partial_failures']}")
    if not isinstance(data.get("processing_time"), (int, float)):
        _fail("missing processing_time")

    server.should_exit = True
    print("OFFLINE SMOKE PASS")
    print(
        json.dumps(
            {
                "texts": len(FIXTURES),
                "dense_dim": DENSE_DIM,
                "sparse_entries": [len(item["indices"]) for item in sparse],
                "colbert_tokens": [len(tokens) for tokens in colbert],
                "processing_time_s": data["processing_time"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
