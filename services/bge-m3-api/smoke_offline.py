"""Offline container smoke for the pinned BGE-M3 artifact (#3366).

Runs INSIDE the built image with ``--network none``: starts the real app
server (its lifespan verifies and loads the pinned artifact), then exercises
``/health`` and the hybrid encode endpoint with Russian, Bulgarian, and
English fixtures, asserting the dense/sparse/ColBERT dimensions,
cardinalities, and finiteness consumed by the application.

The response validation lives in :func:`validate_hybrid_payload` so negative
fixtures (NaN/Infinity, wrong dimensions, empty vector families, partial
failures) are unit-testable without a server; heavy imports are lazy inside
``main()`` for the same reason.

Exit code 0 with ``OFFLINE SMOKE PASS`` proves the artifact loads and serves
every vector family with finite values, no network access, and no warm host
cache.
"""

from __future__ import annotations

import http.client
import json
import math
import sys
import threading
import time


DENSE_DIM = 1024
COLBERT_DIM = 1024
PORT = 8000
STARTUP_TIMEOUT_S = 300.0

FIXTURES = [
    "Привет, мир! Это тестовое предложение для гибридного поиска по квартире.",
    "Здравей, святко! Това е тестово изречение за хибридно търсене.",
    "Hello world! This is a test sentence for hybrid apartment search.",
]


class SmokeCheckError(RuntimeError):
    """A hybrid encode response failed an offline-smoke check."""


def _is_finite_number(value: object) -> bool:
    """True only for real finite ints/floats — NaN, Infinity, bools, and
    strings all fail. NaN survives ``== 0.0`` and ``<= 0`` comparisons, so
    the smoke must gate finiteness explicitly (#3366)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _validate_dense(dense: object, n_texts: int) -> None:
    if not isinstance(dense, list) or len(dense) != n_texts:
        shown = len(dense) if isinstance(dense, list) else type(dense).__name__
        raise SmokeCheckError(f"dense_vecs cardinality {shown} != {n_texts}")
    for i, row in enumerate(dense):
        if not isinstance(row, list) or len(row) != DENSE_DIM:
            shown = len(row) if isinstance(row, list) else type(row).__name__
            raise SmokeCheckError(f"dense_vecs[{i}] dim {shown} != {DENSE_DIM}")
        if all(v == 0.0 for v in row):
            raise SmokeCheckError(f"dense_vecs[{i}] is an all-zero vector")
        for j, value in enumerate(row):
            if not _is_finite_number(value):
                raise SmokeCheckError(f"dense_vecs[{i}][{j}] is not a finite number: {value!r}")


def _validate_sparse(sparse: object, n_texts: int) -> None:
    if not isinstance(sparse, list) or len(sparse) != n_texts:
        shown = len(sparse) if isinstance(sparse, list) else type(sparse).__name__
        raise SmokeCheckError(f"lexical_weights cardinality {shown} != {n_texts}")
    for i, item in enumerate(sparse):
        if not isinstance(item, dict):
            raise SmokeCheckError(f"lexical_weights[{i}] must be an object: {item!r}")
        indices, values = item.get("indices"), item.get("values")
        if not indices or not values or len(indices) != len(values):
            raise SmokeCheckError(f"lexical_weights[{i}] empty or cardinality mismatch: {item!r}")
        for idx in indices:
            if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
                raise SmokeCheckError(f"lexical_weights[{i}] has invalid token index: {idx!r}")
        for value in values:
            if not _is_finite_number(value):
                raise SmokeCheckError(
                    f"lexical_weights[{i}] weight is not a finite number: {value!r}"
                )
            if value <= 0:
                raise SmokeCheckError(f"lexical_weights[{i}] has non-positive weight: {value!r}")


def _validate_colbert(colbert: object, n_texts: int) -> None:
    if not isinstance(colbert, list) or len(colbert) != n_texts:
        shown = len(colbert) if isinstance(colbert, list) else type(colbert).__name__
        raise SmokeCheckError(f"colbert_vecs cardinality {shown} != {n_texts}")
    for i, token_vectors in enumerate(colbert):
        if not token_vectors or not isinstance(token_vectors, list):
            raise SmokeCheckError(f"colbert_vecs[{i}] has no token vectors")
        # Rows beyond a text's real tokens are attention-mask-zeroed pads
        # (canonical FlagEmbedding math), so require real signal per text
        # rather than non-zero rows everywhere.
        if all(all(v == 0.0 for v in row) for row in token_vectors):
            raise SmokeCheckError(f"colbert_vecs[{i}] has no non-zero token vector")
        for j, row in enumerate(token_vectors):
            if not isinstance(row, list) or len(row) != COLBERT_DIM:
                shown = len(row) if isinstance(row, list) else type(row).__name__
                raise SmokeCheckError(f"colbert_vecs[{i}][{j}] dim {shown} != {COLBERT_DIM}")
            for k, value in enumerate(row):
                if not _is_finite_number(value):
                    raise SmokeCheckError(
                        f"colbert_vecs[{i}][{j}][{k}] is not a finite number: {value!r}"
                    )


def validate_hybrid_payload(data: dict, *, n_texts: int | None = None) -> None:
    """Validate a ``/encode/hybrid`` response for the offline smoke (#3366).

    Rejects wrong cardinalities/dimensions, all-zero rows, empty vector
    families, non-numeric and non-finite values (NaN/Infinity pass the legacy
    ``== 0.0`` / ``<= 0`` comparisons and must be rejected explicitly), and
    any partial failures.

    Raises:
        SmokeCheckError: with an actionable message on the first violation.
    """
    if n_texts is None:
        n_texts = len(FIXTURES)

    _validate_dense(data.get("dense_vecs"), n_texts)
    _validate_sparse(data.get("lexical_weights"), n_texts)
    _validate_colbert(data.get("colbert_vecs"), n_texts)

    if data.get("partial_failures"):
        raise SmokeCheckError(f"unexpected partial failure(s): {data['partial_failures']!r}")
    processing_time = data.get("processing_time")
    if not _is_finite_number(processing_time):
        raise SmokeCheckError(f"missing or non-finite processing_time: {processing_time!r}")


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
    # Lazy heavy imports: the validator functions above must stay importable
    # in stdlib-only unit-test environments (negative fixtures, #3366).
    import uvicorn
    from app import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    health: dict | None = None
    while health is None:
        try:
            # Fresh connection per attempt: a refused dial leaves a shared
            # connection in an unrecoverable state.
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
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

    try:
        validate_hybrid_payload(data)
    except SmokeCheckError as exc:
        _fail(str(exc))

    server.should_exit = True
    print("OFFLINE SMOKE PASS")
    print(
        json.dumps(
            {
                "texts": len(FIXTURES),
                "dense_dim": DENSE_DIM,
                "sparse_entries": [len(item["indices"]) for item in data["lexical_weights"]],
                "colbert_tokens": [len(tokens) for tokens in data["colbert_vecs"]],
                "processing_time_s": data["processing_time"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
