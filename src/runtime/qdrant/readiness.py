"""Explicit readiness contracts for the two product Qdrant collections (#3202).

The demo ships two product collections with different roles:

* the configured **knowledge** collection (``QDRANT_COLLECTION``, quantization
  suffix resolved by the caller) answering free-text questions, and
* the hard-coded **apartments** collection backing the catalog/demo flow.

Startup must prove both collections are actually usable *before* Telegram
polling begins: expected vector names and dimensions, payload indexes, and a
non-empty point count. Missing, empty, or schema-incompatible collections are
distinct, actionable failures — never a silent degrade.

The module is transport-neutral (stdlib + ``qdrant_client`` only) so both the
bot preflight and the out-of-process ``scripts/demo_bootstrap.py`` share one
source of truth. Schema, identity, and filter definitions are consumed from
:mod:`src.runtime.qdrant.contracts` — the one authority (#3333); this module
owns readiness *validation* on top of them. It never imports from
``telegram_bot`` (layering ratchet, #1948) and never mutates data: validation
is read-only.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from qdrant_client import AsyncQdrantClient

from src.runtime.qdrant import contracts


logger = logging.getLogger(__name__)

#: BGE-M3 dense dimensionality — canonical value lives in
#: :mod:`src.runtime.qdrant.contracts`; re-exported for consumers of this module.
BGEM3_DENSE_DIM = contracts.BGEM3_DENSE_DIM

#: Hard-coded apartments collection name — canonical value in contracts.
APARTMENTS_COLLECTION = contracts.APARTMENTS_COLLECTION

# ---------------------------------------------------------------------------
# Failure kinds — callers branch on these to give actionable remediation.
# ---------------------------------------------------------------------------

#: Collection does not exist on the server.
KIND_MISSING = "missing"
#: Collection exists but holds zero points.
KIND_EMPTY = "empty"
#: Collection exists but vectors/indexes do not match the contract.
KIND_SCHEMA_INCOMPATIBLE = "schema_incompatible"
#: Collection has points but below the contract minimum.
KIND_INSUFFICIENT_DATA = "insufficient_data"
#: A demo probe matched an unexpected number of results.
KIND_PROBE_MISMATCH = "probe_mismatch"

_REMEDIATION_BOOTSTRAP = "run `make demo-bootstrap` (idempotent, non-destructive)"
_REMEDIATION_ROLLBACK_DOC = "see docs/LOCAL-DEVELOPMENT.md (Demo data readiness) for rollback"


# ---------------------------------------------------------------------------
# Contract dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VectorExpectation:
    """One named vector a collection must provide.

    ``kind`` is ``"dense"`` or ``"sparse"``; ``size`` applies to dense vectors
    only. ``required=False`` marks advisory vectors (missing is a warning, not
    a readiness failure — e.g. ``colbert`` degrades to RRF fallback).
    """

    name: str
    kind: str  # "dense" | "sparse"
    size: int | None = None
    required: bool = True


@dataclass(frozen=True)
class PayloadIndexExpectation:
    """One payload index a collection must provide."""

    field_name: str
    schema_type: str  # PayloadSchemaType value, e.g. "keyword"


@dataclass(frozen=True)
class DemoProbe:
    """A deterministic, embedding-free proof query against prepared data.

    ``filters`` uses the production filter-dict shape shared with the
    apartment filter path: exact match via MatchValue, ``{"gte": .., "lte": ..}``
    dicts via Range, lists via MatchAny. Keys may be top-level payload fields
    (apartments) or ``metadata.*`` paths (knowledge).

    ``expect_results=False`` marks an intentional no-result probe: the demo
    must prove that a legitimate empty search is possible *and distinguishable*
    from missing/empty data.
    """

    name: str
    filters: dict[str, Any]
    expect_results: bool = True
    min_results: int = 1


@dataclass(frozen=True)
class CollectionContract:
    """Explicit readiness contract for one product collection."""

    role: str
    collection_name: str
    dense_vectors: tuple[VectorExpectation, ...]
    sparse_vectors: tuple[VectorExpectation, ...]
    payload_indexes: tuple[PayloadIndexExpectation, ...]
    min_points: int = 1
    demo_probes: tuple[DemoProbe, ...] = ()

    def with_collection_name(self, collection_name: str) -> CollectionContract:
        """Return a copy targeting another physical collection name."""
        return replace(self, collection_name=collection_name)


@dataclass(frozen=True)
class ReadinessFailure:
    """One actionable reason a collection is not ready."""

    collection: str
    kind: str
    message: str
    remediation: str

    def render(self) -> str:
        return f"[{self.kind}] {self.collection}: {self.message} — {self.remediation}"


@dataclass
class CollectionReadiness:
    """Outcome of validating one collection against its contract."""

    collection: str
    role: str
    ok: bool = True
    failures: list[ReadinessFailure] = field(default_factory=list)
    points_count: int | None = None
    probe_results: dict[str, int] = field(default_factory=dict)

    def fail(
        self,
        kind: str,
        message: str,
        remediation: str = _REMEDIATION_BOOTSTRAP,
    ) -> ReadinessFailure:
        failure = ReadinessFailure(
            collection=self.collection,
            kind=kind,
            message=message,
            remediation=remediation,
        )
        self.failures.append(failure)
        self.ok = False
        return failure

    def render(self) -> str:
        return "\n".join(f.render() for f in self.failures)


# ---------------------------------------------------------------------------
# Canonical contracts
# ---------------------------------------------------------------------------


def _indexes(
    index_map: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[PayloadIndexExpectation, ...]:
    """Lift a canonical payload-index map into readiness expectations."""
    return tuple(
        PayloadIndexExpectation(field_name=name, schema_type=schema_type)
        for schema_type, names in index_map
        for name in names
    )


def knowledge_contract(collection_name: str) -> CollectionContract:
    """Contract for the configured knowledge collection."""
    return CollectionContract(
        role="knowledge",
        collection_name=collection_name,
        dense_vectors=(
            VectorExpectation(name=contracts.DENSE_VECTOR, kind="dense", size=BGEM3_DENSE_DIM),
            VectorExpectation(
                name=contracts.COLBERT_VECTOR,
                kind="dense",
                size=BGEM3_DENSE_DIM,
                required=False,
            ),
        ),
        sparse_vectors=(VectorExpectation(name=contracts.SPARSE_VECTOR, kind="sparse"),),
        payload_indexes=_indexes(contracts.KNOWLEDGE_PAYLOAD_INDEXES),
        min_points=1,
    )


def apartments_contract() -> CollectionContract:
    """Contract for the hard-coded apartments collection."""
    return CollectionContract(
        role="apartments",
        collection_name=APARTMENTS_COLLECTION,
        dense_vectors=(
            VectorExpectation(name=contracts.DENSE_VECTOR, kind="dense", size=BGEM3_DENSE_DIM),
            VectorExpectation(
                name=contracts.COLBERT_VECTOR,
                kind="dense",
                size=BGEM3_DENSE_DIM,
                required=False,
            ),
        ),
        sparse_vectors=(VectorExpectation(name=contracts.SPARSE_VECTOR, kind="sparse"),),
        payload_indexes=_indexes(contracts.APARTMENTS_PAYLOAD_INDEXES),
        min_points=1,
    )


# ---------------------------------------------------------------------------
# Shipped demo corpus (knowledge) — data/test/*.md
# ---------------------------------------------------------------------------

#: Point-id namespace so demo corpus points are deterministic and detectable.
DEMO_NAMESPACE = uuid.UUID("7ba7b810-9dad-11d1-80b4-00c04fd430c8")

#: Shipped demo knowledge corpus document ids (Ukrainian legal-code samples).
KNOWLEDGE_DEMO_DOC_IDS = ("article_115", "article_185", "article_190")

#: Anchor document of the shipped demo corpus (first probe below).
#:
#: Attribution note: this is NOT the #3200 known-corpus contract fixture. The
#: live question locked by #3200 — "Сколько стоит студия у моря в Sunny
#: Beach?" with doc id ``sunny_beach_studio`` — exists only as a retrieval
#: stub in tests/characterization/test_grounded_qa_acceptance.py and in the
#: live BGE/Qdrant probe; the shipped Qdrant demo corpus
#: (data/test/*.md) does not contain it. These probes prove
#: the corpus this repo actually ships.
DEMO_CORPUS_ANCHOR_DOC_ID = "article_115"


def knowledge_demo_point_id(doc_id: str) -> str:
    """Deterministic point id for a shipped demo knowledge document."""
    return str(uuid.uuid5(DEMO_NAMESPACE, f"rag-fresh-demo-knowledge:{doc_id}"))


def knowledge_demo_probes() -> tuple[DemoProbe, ...]:
    """Probes proving the shipped demo corpus is present and addressable.

    The first probe anchors on :data:`DEMO_CORPUS_ANCHOR_DOC_ID` — the
    document a corpus-grounded question must be able to find in the prepared
    data. Probes filter ``metadata.doc_id`` — the canonical indexed knowledge
    identifier (#3333) — so a passing probe also proves filter/index agreement.
    A semantic (embedding-backed) proof of the live #3200 known-corpus
    question is a separate live-probe concern, not part of this gate.
    """
    ordered = (
        DEMO_CORPUS_ANCHOR_DOC_ID,
        *(d for d in KNOWLEDGE_DEMO_DOC_IDS if d != DEMO_CORPUS_ANCHOR_DOC_ID),
    )
    return tuple(
        DemoProbe(
            name=f"demo-corpus:{doc_id}",
            filters={"metadata.doc_id": doc_id},
        )
        for doc_id in ordered
    )


# ---------------------------------------------------------------------------
# Shipped demo queries (apartments) — derived from data/apartments.csv
# ---------------------------------------------------------------------------


def apartment_demo_probes(rows: list[dict[str, Any]]) -> tuple[DemoProbe, ...]:
    """Build one probe per distinct advertised filter shape plus a no-result probe.

    Rows are collapsed to their production filter shape (rooms + city/complex
    name): 300 shipped rows advertise only 15 distinct query shapes, so one
    probe per shape exercises the same filter/index path without redundant
    count round-trips (#3333). The final probe is an intentionally impossible
    query proving a legitimate no-result search is distinguishable from
    missing/empty data.
    """
    probes: list[DemoProbe] = []
    seen: set[tuple[tuple[str, Any], ...]] = set()
    for row in rows:
        record_filters: dict[str, Any] = {"rooms": int(row["rooms"])}
        if row.get("city"):
            record_filters["city"] = str(row["city"])
        else:
            record_filters["complex_name"] = str(row["complex_name"])
        shape = tuple(sorted(record_filters.items()))
        if shape in seen:
            continue
        seen.add(shape)
        probes.append(
            DemoProbe(
                name="shipped-shape:" + ":".join(f"{k}={v}" for k, v in shape),
                filters=record_filters,
            )
        )
    probes.append(
        DemoProbe(
            name="intentional-no-result",
            filters={"price_eur": {"lte": 1}},
            expect_results=False,
        )
    )
    return tuple(probes)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _dense_vector_names(info: Any) -> dict[str, Any]:
    vectors = getattr(getattr(getattr(info, "config", None), "params", None), "vectors", None)
    if isinstance(vectors, dict):
        return vectors
    return {}


def _sparse_vector_names(info: Any) -> dict[str, Any]:
    sparse = getattr(getattr(getattr(info, "config", None), "params", None), "sparse_vectors", None)
    if isinstance(sparse, dict):
        return sparse
    return {}


def _payload_schema(info: Any) -> dict[str, Any]:
    schema = getattr(info, "payload_schema", None)
    if isinstance(schema, dict):
        return schema
    return {}


def _index_data_type(schema: Any) -> str | None:
    data_type = getattr(schema, "data_type", None)
    if data_type is None and isinstance(schema, dict):
        data_type = schema.get("data_type")
    if data_type is None:
        return None
    value: Any = getattr(data_type, "value", data_type)
    return value if isinstance(value, str) else str(value)


def _vector_size(params: Any) -> int | None:
    size = getattr(params, "size", None)
    return size if isinstance(size, int) else None


async def validate_collection(
    client: AsyncQdrantClient,
    contract: CollectionContract,
    *,
    run_probes: bool = False,
    probes: tuple[DemoProbe, ...] | None = None,
) -> CollectionReadiness:
    """Validate one collection against its contract (read-only).

    Raises nothing for per-collection problems — failures are returned as
    :class:`ReadinessFailure` items so callers can aggregate actionable
    errors. Connectivity exceptions propagate to the caller (the preflight
    transport fallback relies on that).
    """
    readiness = CollectionReadiness(collection=contract.collection_name, role=contract.role)

    exists = await client.collection_exists(contract.collection_name)
    if not exists:
        readiness.fail(
            KIND_MISSING,
            "collection does not exist",
            remediation=_REMEDIATION_BOOTSTRAP,
        )
        return readiness

    info = await client.get_collection(contract.collection_name)
    readiness.points_count = int(getattr(info, "points_count", 0) or 0)

    # --- Vector contract -------------------------------------------------
    dense = _dense_vector_names(info)
    sparse = _sparse_vector_names(info)
    expectations: tuple[VectorExpectation, ...] = (
        *contract.dense_vectors,
        *contract.sparse_vectors,
    )
    for expectation in expectations:
        registry = dense if expectation.kind == "dense" else sparse
        if expectation.name not in registry:
            if not expectation.required:
                logger.warning(
                    "Readiness WARN: %s collection '%s' missing advisory '%s' vector "
                    "(degrades gracefully)",
                    contract.role,
                    contract.collection_name,
                    expectation.name,
                )
                continue
            readiness.fail(
                KIND_SCHEMA_INCOMPATIBLE,
                f"missing required {expectation.kind} vector '{expectation.name}'",
                remediation=(
                    f"{_REMEDIATION_BOOTSTRAP} after removing the incompatible "
                    f"collection, or re-create it with the documented schema "
                    f"({_REMEDIATION_ROLLBACK_DOC})"
                ),
            )
            continue
        if expectation.kind == "dense":
            actual = _vector_size(registry[expectation.name])
            if actual is not None and actual != expectation.size:
                readiness.fail(
                    KIND_SCHEMA_INCOMPATIBLE,
                    (
                        f"vector '{expectation.name}' is {actual}-dimensional, "
                        f"expected {expectation.size}"
                    ),
                    remediation=(
                        f"{_REMEDIATION_BOOTSTRAP} after migrating the collection "
                        f"({_REMEDIATION_ROLLBACK_DOC})"
                    ),
                )

    # --- Payload-index contract ------------------------------------------
    payload_schema = _payload_schema(info)
    for index_expectation in contract.payload_indexes:
        if index_expectation.field_name not in payload_schema:
            readiness.fail(
                KIND_SCHEMA_INCOMPATIBLE,
                (
                    f"missing payload index '{index_expectation.field_name}' "
                    f"({index_expectation.schema_type})"
                ),
                remediation=(
                    "run `make qdrant-ensure-indexes` (non-destructive) or "
                    f"{_REMEDIATION_BOOTSTRAP}"
                ),
            )
            continue
        actual_type = _index_data_type(payload_schema[index_expectation.field_name])
        if actual_type is not None and actual_type != index_expectation.schema_type:
            readiness.fail(
                KIND_SCHEMA_INCOMPATIBLE,
                (
                    f"payload index '{index_expectation.field_name}' has type "
                    f"'{actual_type}', expected '{index_expectation.schema_type}'"
                ),
                remediation=_REMEDIATION_ROLLBACK_DOC,
            )

    # --- Data contract ----------------------------------------------------
    if readiness.points_count == 0:
        readiness.fail(
            KIND_EMPTY,
            "collection exists but is empty",
            remediation=(
                f"{_REMEDIATION_BOOTSTRAP} to ingest the shipped demo data "
                "(existing collections are never dropped)"
            ),
        )
    elif readiness.points_count < contract.min_points:
        readiness.fail(
            KIND_INSUFFICIENT_DATA,
            f"collection has {readiness.points_count} points, "
            f"expected at least {contract.min_points}",
        )

    # --- Demo probes ------------------------------------------------------
    if run_probes:
        active = contract.demo_probes if probes is None else probes
        await run_demo_probes(client, contract.collection_name, active, readiness)

    return readiness


async def run_demo_probes(
    client: AsyncQdrantClient,
    collection_name: str,
    probes: tuple[DemoProbe, ...],
    readiness: CollectionReadiness | None = None,
) -> dict[str, int]:
    """Run deterministic demo probes and record failures on ``readiness``.

    A probe passes when it matches ``>= min_results`` points (expect_results)
    or exactly zero points (intentional no-result probe). Zero results on an
    expect-results probe is reported as ``probe_mismatch`` — distinct from
    missing/empty/schema failures, because the collection itself is ready and
    only the prepared data does not answer the advertised query.
    """
    outcome = readiness or CollectionReadiness(collection=collection_name, role="probes")
    for probe in probes:
        count = await client.count(
            collection_name=collection_name,
            count_filter=contracts.build_payload_filter(probe.filters),
            exact=True,
        )
        matched = int(count.count)
        outcome.probe_results[probe.name] = matched
        if probe.expect_results and matched < probe.min_results:
            outcome.fail(
                KIND_PROBE_MISMATCH,
                (
                    f"shipped demo query '{probe.name}' returned {matched} results "
                    f"(expected >= {probe.min_results}) — prepared data does not "
                    "answer the advertised query"
                ),
                remediation=(
                    f"{_REMEDIATION_BOOTSTRAP} to re-ingest the shipped demo data "
                    "(populated collections are preserved)"
                ),
            )
        elif not probe.expect_results and matched != 0:
            outcome.fail(
                KIND_PROBE_MISMATCH,
                f"intentional no-result probe '{probe.name}' matched {matched} points",
            )
        else:
            logger.info(
                "Readiness probe OK: %s on '%s' (%d results)",
                probe.name,
                collection_name,
                matched,
            )
    return outcome.probe_results
