"""Qdrant preflight checks for E2E trace gate."""

from __future__ import annotations

import os
from dataclasses import dataclass

from qdrant_client import QdrantClient


@dataclass(frozen=True)
class CollectionRequirement:
    """Requirement for a Qdrant collection."""

    name: str
    min_points: int
    required_vectors: frozenset[str]


@dataclass(frozen=True)
class PreflightResult:
    """Result of Qdrant preflight checks."""

    ok: bool
    message: str
    checked: list[dict[str, object]]


DEFAULT_REQUIREMENTS: tuple[CollectionRequirement, ...] = (
    CollectionRequirement(
        name=os.getenv("E2E_QDRANT_DOC_COLLECTION", "gdrive_documents_bge"),
        min_points=int(os.getenv("E2E_QDRANT_MIN_DOC_POINTS", "1")),
        required_vectors=frozenset(
            v.strip()
            for v in os.getenv("E2E_QDRANT_DOC_VECTORS", "dense,colbert").split(",")
            if v.strip()
        ),
    ),
    CollectionRequirement(
        name=os.getenv("E2E_QDRANT_APARTMENT_COLLECTION", "apartments"),
        min_points=int(os.getenv("E2E_QDRANT_MIN_APARTMENT_POINTS", "1")),
        required_vectors=frozenset(
            v.strip()
            for v in os.getenv("E2E_QDRANT_APARTMENT_VECTORS", "dense,colbert").split(",")
            if v.strip()
        ),
    ),
)


def _vector_names_from_info(info) -> list[str]:
    """Extract vector names from collection info without exposing payload schemas."""
    vectors = getattr(info.config.params, "vectors", None)
    sparse_vectors = getattr(info.config.params, "sparse_vectors", None)
    names: list[str] = []
    if vectors is not None:
        if isinstance(vectors, dict):
            names.extend(vectors.keys())
        elif hasattr(vectors, "vector_name"):
            names.append(vectors.vector_name)
    if sparse_vectors is not None and isinstance(sparse_vectors, dict):
        names.extend(sparse_vectors.keys())
    return names


def run_qdrant_preflight(
    qdrant_url: str | None = None,
    requirements: tuple[CollectionRequirement, ...] | None = None,
) -> PreflightResult:
    """Run Qdrant preflight checks.

    Args:
        qdrant_url: Qdrant server URL. Defaults to QDRANT_URL env var or http://localhost:6333.
        requirements: Collection requirements to validate. Defaults to DEFAULT_REQUIREMENTS.

    Returns:
        PreflightResult with ok status, sanitized message, and checked details.
    """
    url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
    reqs = requirements if requirements is not None else DEFAULT_REQUIREMENTS

    checked: list[dict[str, object]] = []
    failures: list[str] = []

    try:
        client = QdrantClient(url=url)
    except Exception as exc:
        return PreflightResult(
            ok=False,
            message=f"Qdrant connection failed: {exc}",
            checked=[],
        )

    for req in reqs:
        item: dict[str, object] = {
            "collection": req.name,
            "exists": False,
            "points_count": 0,
            "vectors": [],
        }

        try:
            exists = client.collection_exists(req.name)
            item["exists"] = exists

            if not exists:
                failures.append(
                    f"Collection '{req.name}' does not exist. "
                    "Ensure the collection is created and indexed before running E2E traces."
                )
                checked.append(item)
                continue

            info = client.get_collection(req.name)
            points_count = getattr(info, "points_count", 0)
            item["points_count"] = points_count

            vector_names = _vector_names_from_info(info)
            item["vectors"] = vector_names

            if points_count < req.min_points:
                failures.append(
                    f"Collection '{req.name}' has {points_count} points "
                    f"(minimum required: {req.min_points}). "
                    "Re-index data to meet the threshold."
                )

            missing_vectors = req.required_vectors - set(vector_names)
            if missing_vectors:
                failures.append(
                    f"Collection '{req.name}' missing required vectors: {sorted(missing_vectors)}. "
                    "Recreate the collection with the required vector configurations."
                )
        except Exception as exc:
            failures.append(
                f"Collection '{req.name}' check failed: {exc}. "
                "Verify Qdrant is reachable and the collection schema is valid."
            )

        checked.append(item)

    if failures:
        return PreflightResult(
            ok=False,
            message="Qdrant preflight failed:\n- " + "\n- ".join(failures),
            checked=checked,
        )

    return PreflightResult(
        ok=True,
        message="Qdrant preflight passed",
        checked=checked,
    )
