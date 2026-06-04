"""Ephemeral Qdrant collection helpers for simplification E2E tests.

Provides safe, isolated collection creation with unique names and a
default-delete-after-test policy.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


def generate_collection_name() -> str:
    """Return a unique collection name with ``e2e_core_`` prefix.

    Uses a hex UUID suffix for collision resistance.  Format:
    ``e2e_core_<16 hex chars>``.
    """
    return f"e2e_core_{uuid.uuid4().hex[:16]}"


def should_keep_collection() -> bool:
    """Return True when ``E2E_KEEP_COLLECTION=1`` (truthy)."""
    env = os.getenv("E2E_KEEP_COLLECTION", "")
    return bool(env) and env != "0"


@dataclass
class QdrantTestContext:
    """Metadata bag for an ephemeral test Qdrant collection.

    Attributes:
        collection_name: Unique collection name (``e2e_core_<uuid>``).
        qdrant_url: Qdrant server URL used for the test.
        keep: Whether the collection should survive after the test.
    """

    collection_name: str
    qdrant_url: str
    keep: bool
