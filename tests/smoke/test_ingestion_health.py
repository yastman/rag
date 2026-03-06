"""Smoke tests: verify gdrive_documents_bge collection is populated and searchable."""

import json
import os
import socket
import urllib.request

import pytest


QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
BGE_M3_URL = os.getenv("BGE_M3_URL", "http://localhost:8000")
COLLECTION = os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_bge")


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def _http_post(url: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _require_qdrant() -> None:
    if not _port_open("localhost", 6333):
        pytest.skip("Qdrant not running on localhost:6333")


def _require_bge_m3() -> None:
    if not _port_open("localhost", 8000):
        pytest.skip("BGE-M3 not running on localhost:8000")


class TestIngestionHealth:
    """Verify gdrive_documents_bge collection is populated after ingestion."""

    def test_collection_exists(self) -> None:
        _require_qdrant()
        result = _http_get(f"{QDRANT_URL}/collections")
        names = [c["name"] for c in result["result"]["collections"]]
        assert COLLECTION in names, f"Collection '{COLLECTION}' not found. Available: {names}"

    def test_collection_not_empty(self) -> None:
        _require_qdrant()
        result = _http_get(f"{QDRANT_URL}/collections/{COLLECTION}")
        points = result["result"]["points_count"]
        assert points > 0, (
            f"Collection '{COLLECTION}' is empty (0 points). "
            "Run 'make ingest-local' to populate it."
        )

    def test_documents_have_text_payload(self) -> None:
        _require_qdrant()
        result = _http_post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
            {"limit": 1, "with_payload": True, "with_vector": False},
        )
        points = result.get("result", {}).get("points", [])
        assert points, "No points returned from scroll"
        payload = points[0].get("payload", {})
        assert "text" in payload, f"Point payload missing 'text': {list(payload.keys())}"
        assert len(payload["text"]) > 10, "Text payload is too short"

    def test_documents_have_doc_id(self) -> None:
        _require_qdrant()
        result = _http_post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
            {"limit": 1, "with_payload": True, "with_vector": False},
        )
        points = result.get("result", {}).get("points", [])
        assert points, "No points returned"
        metadata = points[0].get("payload", {}).get("metadata", {})
        assert "doc_id" in metadata, f"Missing doc_id in metadata: {list(metadata.keys())}"


class TestHybridSearch:
    """Verify hybrid search returns meaningful results."""

    QUERY = "виды ВНЖ в Болгарии"

    def _dense_embedding(self, text: str) -> list[float]:
        result = _http_post(f"{BGE_M3_URL}/encode/dense", {"texts": [text]})
        return result["dense_vecs"][0]

    def _sparse_embedding(self, text: str) -> tuple[list[int], list[float]]:
        result = _http_post(f"{BGE_M3_URL}/encode/sparse", {"texts": [text]})
        sparse = result["lexical_weights"][0]
        return sparse["indices"], sparse["values"]

    def test_dense_search_returns_results(self) -> None:
        _require_qdrant()
        _require_bge_m3()
        dense_vec = self._dense_embedding(self.QUERY)
        result = _http_post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/query",
            {"query": dense_vec, "using": "dense", "limit": 5, "with_payload": False},
        )
        hits = result.get("result", {}).get("points", [])
        assert len(hits) > 0, f"Dense search returned no results for: '{self.QUERY}'"

    def test_hybrid_search_returns_results(self) -> None:
        _require_qdrant()
        _require_bge_m3()
        dense_vec = self._dense_embedding(self.QUERY)
        sparse_idx, sparse_vals = self._sparse_embedding(self.QUERY)
        payload = {
            "prefetch": [
                {"query": dense_vec, "using": "dense", "limit": 10},
                {
                    "query": {"indices": sparse_idx, "values": sparse_vals},
                    "using": "bm42",
                    "limit": 10,
                },
            ],
            "query": {"fusion": "rrf"},
            "limit": 5,
            "with_payload": True,
        }
        result = _http_post(f"{QDRANT_URL}/collections/{COLLECTION}/points/query", payload)
        hits = result.get("result", {}).get("points", [])
        assert len(hits) > 0, f"Hybrid search returned no results for: '{self.QUERY}'"
        # Top result must have text
        text = hits[0].get("payload", {}).get("text", "")
        assert text, "Top result payload has no text field"
