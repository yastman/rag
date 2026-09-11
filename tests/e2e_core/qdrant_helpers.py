"""Run-owned Qdrant collection policy for the live E2E harness (#3414).

Every write-oriented live test owns resources only under the
``rag_e2e_<run-id>_<worker>`` namespace.  Known production collection names
are rejected everywhere, ownership is validated before any create/delete,
and names are generated with a UUID suffix for collision resistance.

This module is stdlib-only so that ``tests/conftest.py`` can import the
safety policy without pulling service clients into every test tier.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass


class HarnessSafetyError(RuntimeError):
    """A harness safety invariant was violated (ownership, endpoint, policy)."""


RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")
WORKER_RE = re.compile(r"^(main|gw\d{1,3})$")
OWNED_COLLECTION_PREFIX = "rag_e2e_"
RUN_ID_LENGTH = 12

# Known production/canonical collection names (compose.yml, telegram_bot
# defaults, and their quantization variants).  Test writes must never touch
# them; the harness refuses to create or delete under these names.
PRODUCTION_COLLECTION_NAMES: frozenset[str] = frozenset(
    {
        "gdrive_documents_bge",
        "gdrive_documents_bge_scalar",
        "gdrive_documents_bge_binary",
        "file_documents_bge",
    }
)


def validate_run_id(run_id: str) -> str:
    """Return ``run_id`` when it is a 12-char hex label; raise otherwise."""
    if not RUN_ID_RE.match(run_id or ""):
        raise HarnessSafetyError(
            f"run id {run_id!r} must be 12 lowercase hex chars "
            "(E2E_RUN_ID); refusing unlabeled resources"
        )
    return run_id


def validate_worker(worker: str) -> str:
    """Return ``worker`` when it is ``main``/``gw<N>``; raise otherwise."""
    if not WORKER_RE.match(worker or ""):
        raise HarnessSafetyError(
            f"worker label {worker!r} must be 'main' or 'gw<N>' (PYTEST_XDIST_WORKER)"
        )
    return worker


def production_collection_names() -> frozenset[str]:
    """The blocked production collection names."""
    return PRODUCTION_COLLECTION_NAMES


def generate_collection_name(run_id: str, worker: str) -> str:
    """Return a unique run-owned collection name.

    Format: ``rag_e2e_<run-id>_<worker>_<16 hex chars>`` so two xdist
    workers (and two concurrent runs) can never share a collection.
    """
    validate_run_id(run_id)
    validate_worker(worker)
    return f"{OWNED_COLLECTION_PREFIX}{run_id}_{worker}_{uuid.uuid4().hex[:16]}"


def is_owned_collection_name(name: str, run_id: str) -> bool:
    """True when ``name`` belongs to the given run's namespace."""
    try:
        validate_run_id(run_id)
    except HarnessSafetyError:
        return False
    return isinstance(name, str) and name.startswith(f"{OWNED_COLLECTION_PREFIX}{run_id}_")


def assert_owned_collection_name(name: str, run_id: str) -> str:
    """Return ``name`` when run-owned; raise for anything else.

    Refuses known production names, foreign-run names, and unlabeled/shared
    names — this guard runs BEFORE both create and delete so the harness can
    never write outside (or clean inside) another namespace.
    """
    validate_run_id(run_id)
    if name in PRODUCTION_COLLECTION_NAMES:
        raise HarnessSafetyError(
            f"refusing production collection name {name!r}: live tests own only "
            f"{OWNED_COLLECTION_PREFIX}<run-id>_<worker>_* resources (#3414)"
        )
    if not is_owned_collection_name(name, run_id):
        raise HarnessSafetyError(
            f"refusing non-owned collection name {name!r}: it does not belong to "
            f"run namespace {OWNED_COLLECTION_PREFIX}{run_id}_*"
        )
    return name


def assert_owned_collection_format(name: str) -> str:
    """Return ``name`` when it matches the rag_e2e_<run-id>_* shape.

    Weaker than :func:`assert_owned_collection_name` (any run id accepted);
    quantization-variant suffixes (``_binary``/``_scalar``) are allowed.
    """
    if not isinstance(name, str) or not re.fullmatch(
        rf"{OWNED_COLLECTION_PREFIX}[0-9a-f]{{12}}_[A-Za-z0-9]+_[0-9a-f]+(?:_(?:binary|scalar))?",
        name,
    ):
        raise HarnessSafetyError(
            f"refusing collection name {name!r}: live harness collections must be "
            f"{OWNED_COLLECTION_PREFIX}<12-hex-run-id>_<worker>_<uuid> (#3414)"
        )
    return name


def should_keep_collection() -> bool:
    """Return True when ``E2E_KEEP_COLLECTION=1`` (truthy debug override)."""
    env = os.environ.get("E2E_KEEP_COLLECTION", "").strip().lower()
    return bool(env) and env not in {"0", "false", "no", "off"}


@dataclass
class QdrantTestContext:
    """Metadata bag for an ephemeral, run-owned test Qdrant collection.

    Attributes:
        collection_name: Run-owned name (``rag_e2e_<run-id>_<worker>_<uuid>``).
        qdrant_url: Qdrant server URL used for the test.
        keep: Whether the collection should survive after the test.
        run_id: Owning run id (empty for legacy call sites).
    """

    collection_name: str
    qdrant_url: str
    keep: bool
    run_id: str = ""

    def __post_init__(self) -> None:
        if self.run_id:
            validate_run_id(self.run_id)
            assert_owned_collection_name(self.collection_name, self.run_id)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"QdrantTestContext(collection_name={self.collection_name!r}, "
            f"qdrant_url={self.qdrant_url!r}, keep={self.keep!r}, "
            f"run_id={self.run_id!r})"
        )


def iter_blocked(names: Iterable[str], run_id: str) -> list[str]:
    """Return the subset of ``names`` the ownership guard would reject."""
    blocked: list[str] = []
    for name in names:
        try:
            assert_owned_collection_name(name, run_id)
        except HarnessSafetyError:
            blocked.append(name)
    return blocked
