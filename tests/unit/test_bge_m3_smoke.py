"""Negative smoke fixtures for the offline BGE-M3 three-vector proof (#3366).

The offline smoke must reject non-finite values explicitly: NaN survives the
dimension/nonzero/positive comparisons the smoke previously relied on, so a
degenerate model could pass while producing garbage vectors. These tests feed
poisoned hybrid payloads to the smoke's validator and assert rejection with
actionable messages. Stdlib-only: imports ``smoke_offline`` without starting
a server (heavy imports are lazy inside ``main()``).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest


_REPO_ROOT = Path(__file__).parents[2]
_SERVICE_DIR = _REPO_ROOT / "services" / "bge-m3-api"

sys.path.insert(0, str(_SERVICE_DIR))

from smoke_offline import DENSE_DIM, FIXTURES, SmokeCheckError, validate_hybrid_payload


N_TEXTS = len(FIXTURES)


def _valid_payload() -> dict[str, Any]:
    return {
        "dense_vecs": [[0.1] * DENSE_DIM for _ in range(N_TEXTS)],
        "lexical_weights": [{"indices": [5, 9], "values": [0.5, 1.5]} for _ in range(N_TEXTS)],
        "colbert_vecs": [[[0.1] * DENSE_DIM, [0.2] * DENSE_DIM] for _ in range(N_TEXTS)],
        "processing_time": 0.5,
        "partial_failures": [],
    }


# ── Positive control ───────────────────────────────────────────────────────────


def test_valid_payload_passes() -> None:
    validate_hybrid_payload(_valid_payload())


# ── Finiteness: NaN/Infinity must be rejected in every vector family ──────────


def test_nan_dense_value_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"][1][7] = float("nan")
    with pytest.raises(SmokeCheckError, match=r"dense_vecs\[1\]\[7\].*finite"):
        validate_hybrid_payload(payload)


def test_infinite_dense_value_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"][0][0] = float("inf")
    with pytest.raises(SmokeCheckError, match=r"dense_vecs\[0\]\[0\].*finite"):
        validate_hybrid_payload(payload)


def test_nan_sparse_weight_rejected() -> None:
    payload = _valid_payload()
    payload["lexical_weights"][2]["values"][0] = float("nan")
    with pytest.raises(SmokeCheckError, match=r"lexical_weights\[2\].*finite"):
        validate_hybrid_payload(payload)


def test_infinite_sparse_weight_rejected() -> None:
    payload = _valid_payload()
    payload["lexical_weights"][0]["values"][1] = math.inf
    with pytest.raises(SmokeCheckError, match=r"lexical_weights\[0\].*finite"):
        validate_hybrid_payload(payload)


def test_nan_colbert_value_rejected() -> None:
    payload = _valid_payload()
    payload["colbert_vecs"][1][0][3] = float("nan")
    with pytest.raises(SmokeCheckError, match=r"colbert_vecs\[1\]\[0\].*finite"):
        validate_hybrid_payload(payload)


def test_infinite_colbert_value_rejected() -> None:
    payload = _valid_payload()
    payload["colbert_vecs"][0][1][5] = -math.inf
    with pytest.raises(SmokeCheckError, match=r"colbert_vecs\[0\]\[1\].*finite"):
        validate_hybrid_payload(payload)


def test_nan_survives_legacy_comparisons() -> None:
    """Lock the audit's finding: NaN passes == 0.0, <= 0, and dimension checks,
    which is exactly why the explicit finiteness gate must exist."""
    nan = float("nan")
    assert (nan == 0.0) is False
    assert (nan <= 0) is False
    assert len([nan] * DENSE_DIM) == DENSE_DIM


def test_non_numeric_dense_value_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"][2][0] = "0.1"
    with pytest.raises(SmokeCheckError, match=r"dense_vecs\[2\]\[0\]"):
        validate_hybrid_payload(payload)


# ── Dimensions and cardinality ─────────────────────────────────────────────────


def test_wrong_dense_dimension_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"][0] = [0.1] * 768
    with pytest.raises(SmokeCheckError, match=r"dense_vecs\[0\].*dim.*768"):
        validate_hybrid_payload(payload)


def test_wrong_colbert_dimension_rejected() -> None:
    payload = _valid_payload()
    payload["colbert_vecs"][0][0] = [0.1] * 512
    with pytest.raises(SmokeCheckError, match=r"colbert_vecs\[0\]\[0\].*dim.*512"):
        validate_hybrid_payload(payload)


def test_dense_cardinality_mismatch_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"] = payload["dense_vecs"][:1]
    with pytest.raises(SmokeCheckError, match="dense_vecs"):
        validate_hybrid_payload(payload)


def test_sparse_index_value_cardinality_mismatch_rejected() -> None:
    payload = _valid_payload()
    payload["lexical_weights"][1] = {"indices": [5, 9], "values": [0.5]}
    with pytest.raises(SmokeCheckError, match=r"lexical_weights\[1\]"):
        validate_hybrid_payload(payload)


def test_negative_sparse_weight_rejected() -> None:
    payload = _valid_payload()
    payload["lexical_weights"][0]["values"][0] = -0.5
    with pytest.raises(SmokeCheckError, match=r"lexical_weights\[0\].*positive"):
        validate_hybrid_payload(payload)


# ── Empty vector families and partial failures ────────────────────────────────


def test_empty_dense_family_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"] = []
    with pytest.raises(SmokeCheckError, match="dense_vecs"):
        validate_hybrid_payload(payload)


def test_empty_sparse_family_rejected() -> None:
    payload = _valid_payload()
    payload["lexical_weights"] = []
    with pytest.raises(SmokeCheckError, match="lexical_weights"):
        validate_hybrid_payload(payload)


def test_empty_colbert_family_rejected() -> None:
    payload = _valid_payload()
    payload["colbert_vecs"] = []
    with pytest.raises(SmokeCheckError, match="colbert_vecs"):
        validate_hybrid_payload(payload)


def test_all_zero_dense_vector_rejected() -> None:
    payload = _valid_payload()
    payload["dense_vecs"][1] = [0.0] * DENSE_DIM
    with pytest.raises(SmokeCheckError, match=r"dense_vecs\[1\].*zero"):
        validate_hybrid_payload(payload)


def test_empty_sparse_entry_rejected() -> None:
    payload = _valid_payload()
    payload["lexical_weights"][1] = {"indices": [], "values": []}
    with pytest.raises(SmokeCheckError, match=r"lexical_weights\[1\].*empty"):
        validate_hybrid_payload(payload)


def test_partial_failures_rejected() -> None:
    payload = _valid_payload()
    payload["partial_failures"] = [{"index": 2, "error": "empty or whitespace-only string"}]
    with pytest.raises(SmokeCheckError, match="partial failure"):
        validate_hybrid_payload(payload)


def test_missing_processing_time_rejected() -> None:
    payload = _valid_payload()
    del payload["processing_time"]
    with pytest.raises(SmokeCheckError, match="processing_time"):
        validate_hybrid_payload(payload)


def test_validator_handles_json_nan_constants() -> None:
    """Python's JSON encoder/decoder round-trips NaN as the non-standard
    ``NaN`` constant; the validator must reject a payload that carries it
    through the wire format instead of tripping on structure first."""
    raw = json.loads(
        json.dumps(
            {
                "dense_vecs": [[float("nan")] + [0.1] * (DENSE_DIM - 1)],
                "lexical_weights": [],
                "colbert_vecs": [],
            }
        )
    )
    assert json.dumps(raw).startswith('{"dense_vecs": [[NaN'), "expected NaN constant"
    with pytest.raises(SmokeCheckError, match="finite"):
        validate_hybrid_payload(raw, n_texts=1)
