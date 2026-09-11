"""Strict Qdrant-only operational acceptance gate (#3458).

One live lane proving the database is USEFUL, not merely listening: a fresh
run-owned collection with the production schema receives dense + sparse +
ColBERT points, answers retrieval through the production
:class:`~src.runtime.services.qdrant.QdrantService` (RRF fusion and server-side
ColBERT MaxSim reranking), and survives a controlled container restart.
Deterministic unit vectors isolate the Qdrant boundary — no BGE, no LLM, no
Redis, no PostgreSQL, no Telegram, no external network.

Scenario coverage (issue #3458):

1. Fresh unique collection matches the #3333 production contract
   (1024-dim ``dense`` COSINE, ``bm42`` sparse, ``colbert`` MAX_SIM
   multivector) — asserted from the live collection info.
2. Two deterministic points upserted with the production payload shape
   (``page_content`` + ``metadata``).
3. Exact count and scroll/read proof of all three vector kinds.
4. ``QdrantService.hybrid_search_rrf`` dense+sparse fusion returns the
   expected top-1 id AND payload — in both directions.
5. ``QdrantService.hybrid_search_rrf_colbert`` proves ColBERT was actually
   applied (``colbert_applied=True``, no ``fallback_reason``, MaxSim score)
   and returns the expected top-1.
6. A missing collection raises; a schema-incompatible collection yields
   actionable non-success search results (``backend_error`` meta, ColBERT
   reported as unavailable) — a listening-but-unusable Qdrant cannot go green.
7. Opt-in isolated restart (``QDRANT_E2E_RESTART_PROJECT``): count and both
   search results are unchanged after bounded readiness waiting.
8. ``finally`` teardown deletes only the exact run-owned collection and
   proves it is absent.

Strict lane conventions (#3368 model): ``QDRANT_E2E_STRICT=1`` turns an
unavailable Qdrant into a FAILURE instead of a skip. The restart case is
opt-in destructive: it is only collected when ``QDRANT_E2E_RESTART_PROJECT``
names an explicitly supplied disposable Compose project, and it refuses to
restart anything else.

Provisioning: collections are provisioned through the harness canonical
``recreate_collection`` (#3414) — the same production vector contract the
#3416 ingestion lane uses. Explicit ``cmd_bootstrap`` is intentionally not
used: its strict-mode guardrails currently reject the scroll/write page
sizes the production paths need (live-reproduced bug, tracked for #3459).
Schema identity is asserted against ``src.runtime.qdrant.contracts`` (#3333).

Canonical runs (zero skips when ``QDRANT_E2E_STRICT=1`` and the restart case
is selected)::

    QDRANT_URL=http://localhost:6333 QDRANT_E2E_STRICT=1 \\
        uv run --frozen pytest -q tests/e2e_core/test_qdrant_operational_live.py \\
        -m requires_services -rs

    QDRANT_URL=http://127.0.0.1:6333 QDRANT_E2E_STRICT=1 \\
        QDRANT_E2E_RESTART_PROJECT=rag-e2e-<12-hex-run-id> \\
        uv run --frozen pytest -q tests/e2e_core/test_qdrant_operational_live.py \\
        -m requires_services -rs
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from qdrant_client import QdrantClient, models

from src.runtime.qdrant import contracts
from src.runtime.services.qdrant import QdrantService
from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    RunNamespace,
    TeardownRegistry,
    make_qdrant_context,
    recreate_collection,
)
from tests.e2e_core.qdrant_helpers import (
    QdrantTestContext,
    generate_collection_name,
    production_collection_names,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

_TRUTHY = {"1", "true", "yes", "on"}
# Disposable Compose projects follow the harness convention (#3414):
# ``compose_project_name(run_id) == "rag-e2e-<12-hex>"``. Nothing else may be
# restarted by this lane — not the developer stack, not a VPS stack, nothing.
_DISPOSABLE_PROJECT_RE = re.compile(r"^rag-e2e-[0-9a-f]{12}$")
_QDRANT_COMPOSE_SERVICE = "qdrant"
_READINESS_DEADLINE_S = 120.0


def _strict_lane() -> bool:
    return os.getenv("QDRANT_E2E_STRICT", "").strip().lower() in _TRUTHY


def _service_guard(reason: str) -> None:
    """Fail in the strict Qdrant lane, skip otherwise (#3368 convention)."""
    if _strict_lane():
        pytest.fail(reason)
    pytest.skip(f"{reason} (set QDRANT_E2E_STRICT=1 to make this a failure)")


async def _require_qdrant(env: LiveE2EEnv) -> None:
    """The gate needs a reachable Qdrant; strict mode fails instead of skipping."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{env.qdrant_url.rstrip('/')}/collections")
            response.raise_for_status()
    except Exception as exc:
        _service_guard(f"Qdrant unavailable at {env.qdrant_url}: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Fixtures: run-owned namespace with leak-proof teardown (#3414)
# ---------------------------------------------------------------------------


@pytest.fixture
def harness_env() -> LiveE2EEnv:
    """Loopback-enforced Qdrant endpoint resolution (``QDRANT_URL``)."""
    return LiveE2EEnv.from_env()


@pytest.fixture
def run_namespace() -> RunNamespace:
    """One run id per invocation (pinned by ``tests/conftest.py``)."""
    return RunNamespace.resolve()


@pytest.fixture
async def owned_registry(
    harness_env: LiveE2EEnv, run_namespace: RunNamespace
) -> AsyncIterator[TeardownRegistry]:
    """Teardown registry that deletes only run-owned state and proves zero leaks.

    The availability guard runs at fixture SETUP so an unreachable Qdrant
    yields a clean skip (strict: failure) — never a provisioning error and
    never a half-created resource.
    """
    await _require_qdrant(harness_env)

    registry = TeardownRegistry(run_id=run_namespace.run_id)
    yield registry
    await registry.teardown_and_verify()


@pytest.fixture
async def owned_collection(
    harness_env: LiveE2EEnv, owned_registry: TeardownRegistry
) -> QdrantTestContext:
    """Fresh run-owned collection with the production vector contract."""
    context = make_qdrant_context(harness_env)
    owned_registry.register_collection(harness_env.qdrant_url, context.collection_name)
    recreate_collection(harness_env, context.collection_name)
    return context


# ---------------------------------------------------------------------------
# Deterministic fixtures: unit vectors with disjoint support per point
# ---------------------------------------------------------------------------

_DIM = contracts.BGEM3_DENSE_DIM

ALPHA_DOC_ID = "gate-alpha"
BETA_DOC_ID = "gate-beta"
ALPHA_TEXT = "Alpha datum: the qdrant operational gate retrieves the alpha record."
BETA_TEXT = "Beta datum: the qdrant operational gate retrieves the beta record."

# Deterministic UUID5 ids: identical across runs, never reused by production.
ALPHA_POINT_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "issue-3458/qdrant-gate/alpha"))
BETA_POINT_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "issue-3458/qdrant-gate/beta"))


def _unit(index: int) -> list[float]:
    vector = [0.0] * _DIM
    vector[index] = 1.0
    return vector


def _gate_payload(doc_id: str, text: str) -> dict[str, Any]:
    """The production payload shape written by the unified writer."""
    return {
        "page_content": text,
        "metadata": {
            "doc_id": doc_id,
            "source": "issue-3458-gate",
            "source_type": "test",
            "language": "en",
        },
    }


def _gate_points() -> list[models.PointStruct]:
    """Two deterministic points carrying complete dense + sparse + ColBERT."""
    return [
        models.PointStruct(
            id=ALPHA_POINT_ID,
            vector={
                contracts.DENSE_VECTOR: _unit(0),
                contracts.SPARSE_VECTOR: models.SparseVector(indices=[101], values=[1.0]),
                contracts.COLBERT_VECTOR: [_unit(0), _unit(1)],
            },
            payload=_gate_payload(ALPHA_DOC_ID, ALPHA_TEXT),
        ),
        models.PointStruct(
            id=BETA_POINT_ID,
            vector={
                contracts.DENSE_VECTOR: _unit(1),
                contracts.SPARSE_VECTOR: models.SparseVector(indices=[202], values=[1.0]),
                contracts.COLBERT_VECTOR: [_unit(2), _unit(3)],
            },
            payload=_gate_payload(BETA_DOC_ID, BETA_TEXT),
        ),
    ]


# Query fixtures: each query matches exactly one point on every vector kind,
# so both search paths must rank that point first — a listening-but-broken
# server cannot fake the ids, payloads, or scores asserted below.
ALPHA_QUERY_DENSE = _unit(0)
ALPHA_QUERY_SPARSE = {"indices": [101], "values": [1.0]}
ALPHA_QUERY_COLBERT = [_unit(0), _unit(1)]  # MaxSim vs alpha rows = exactly 2.0
BETA_QUERY_DENSE = _unit(1)
BETA_QUERY_SPARSE = {"indices": [202], "values": [1.0]}
BETA_QUERY_COLBERT = [_unit(2), _unit(3)]  # MaxSim vs beta rows = exactly 2.0


def _client(harness_env: LiveE2EEnv, timeout: int = 30) -> QdrantClient:
    return QdrantClient(
        url=harness_env.qdrant_url, api_key=harness_env.qdrant_api_key, timeout=timeout
    )


def _upsert_gate_points(harness_env: LiveE2EEnv, collection_name: str) -> None:
    """Write the two deterministic gate points (synchronous commit)."""
    client = _client(harness_env)
    try:
        operation = client.upsert(collection_name=collection_name, points=_gate_points(), wait=True)
        assert operation.status == models.UpdateStatus.COMPLETED, operation.status
    finally:
        client.close()


def _production_service(harness_env: LiveE2EEnv, collection_name: str) -> QdrantService:
    """The production gateway under test — never a re-implementation."""
    return QdrantService(
        url=harness_env.qdrant_url,
        api_key=harness_env.qdrant_api_key,
        collection_name=collection_name,
        timeout=30,
        prefer_grpc=False,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — the provisioned schema matches the #3333 production contract
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_collection_schema_matches_production_contract(
    harness_env: LiveE2EEnv, owned_collection: QdrantTestContext
) -> None:
    """Fresh unique collection: dense 1024 COSINE + bm42 sparse + colbert MAX_SIM."""
    client = _client(harness_env)
    try:
        info = client.get_collection(owned_collection.collection_name)
    finally:
        client.close()

    params = info.config.params
    assert isinstance(params.vectors, dict), "production collections use named vectors"
    dense = params.vectors[contracts.DENSE_VECTOR]
    assert dense.size == contracts.BGEM3_DENSE_DIM
    assert dense.distance == models.Distance.COSINE

    colbert = params.vectors[contracts.COLBERT_VECTOR]
    assert colbert.size == contracts.BGEM3_DENSE_DIM
    assert colbert.multivector_config is not None
    assert colbert.multivector_config.comparator == models.MultiVectorComparator.MAX_SIM

    assert params.sparse_vectors is not None
    assert contracts.SPARSE_VECTOR in params.sparse_vectors, (
        "the knowledge sparse field must be declared under its canonical name"
    )

    # The name is run-owned and unpredictable: this run's namespace prefix and
    # never one of the production collections.
    run_id = RunNamespace.resolve().run_id
    assert owned_collection.collection_name.startswith(f"rag_e2e_{run_id}_")
    assert owned_collection.collection_name not in production_collection_names()


# ---------------------------------------------------------------------------
# Scenario 2 + 3 — deterministic writes, exact count, scroll/read proof
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_upsert_two_points_count_and_scroll_prove_three_vector_kinds(
    harness_env: LiveE2EEnv, owned_collection: QdrantTestContext
) -> None:
    """Exactly two points land; scroll reads payloads and all three vector kinds."""
    _upsert_gate_points(harness_env, owned_collection.collection_name)

    client = _client(harness_env)
    try:
        assert client.count(collection_name=owned_collection.collection_name).count == 2
        records, offset = client.scroll(
            collection_name=owned_collection.collection_name,
            limit=10,
            with_payload=True,
            with_vectors=True,
        )
    finally:
        client.close()
    assert offset is None, "two points must fit in one scroll page"

    by_id = {str(record.id): record for record in records}
    assert set(by_id) == {ALPHA_POINT_ID, BETA_POINT_ID}

    for point_id, doc_id, text in (
        (ALPHA_POINT_ID, ALPHA_DOC_ID, ALPHA_TEXT),
        (BETA_POINT_ID, BETA_DOC_ID, BETA_TEXT),
    ):
        record = by_id[point_id]
        assert record.payload is not None
        assert record.payload["page_content"] == text
        assert record.payload["metadata"]["doc_id"] == doc_id
        assert record.payload["metadata"]["source"] == "issue-3458-gate"

        # Named-vector collections return the vector dict; the shape
        # assertions below are the real proof, typing is kept loose on purpose.
        raw_vectors = record.vector
        assert isinstance(raw_vectors, dict), "named vectors must scroll back as a dict"
        vectors: dict[str, Any] = dict(raw_vectors)
        assert set(vectors) == {
            contracts.DENSE_VECTOR,
            contracts.SPARSE_VECTOR,
            contracts.COLBERT_VECTOR,
        }, f"point must carry the complete named-vector set, got {sorted(vectors)}"
        assert len(vectors[contracts.DENSE_VECTOR]) == contracts.BGEM3_DENSE_DIM
        sparse = vectors[contracts.SPARSE_VECTOR]
        assert isinstance(sparse, models.SparseVector)
        assert len(sparse.indices) > 0
        assert len(sparse.indices) == len(sparse.values)
        colbert_rows = vectors[contracts.COLBERT_VECTOR]
        assert isinstance(colbert_rows, list) and len(colbert_rows) > 0
        for row in colbert_rows:
            assert isinstance(row, list), "colbert multivectors must be lists of 1024-dim rows"
            assert len(row) == contracts.BGEM3_DENSE_DIM


# ---------------------------------------------------------------------------
# Scenario 4 — production RRF hybrid search returns the expected top-1
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_production_hybrid_search_rrf_returns_expected_top1(
    harness_env: LiveE2EEnv, owned_collection: QdrantTestContext
) -> None:
    """Dense+sparse RRF fusion through QdrantService ranks the matched point first."""
    _upsert_gate_points(harness_env, owned_collection.collection_name)
    service = _production_service(harness_env, owned_collection.collection_name)
    try:
        results, meta = await service.hybrid_search_rrf(
            dense_vector=ALPHA_QUERY_DENSE,
            sparse_vector=ALPHA_QUERY_SPARSE,
            top_k=5,
            return_meta=True,
        )
        assert meta["backend_error"] is False, meta
        assert [result["id"] for result in results] == [ALPHA_POINT_ID, BETA_POINT_ID]
        assert results[0]["text"] == ALPHA_TEXT
        assert results[0]["metadata"]["doc_id"] == ALPHA_DOC_ID

        # The reverse query proves the ranking is content-driven, not accidental.
        results, meta = await service.hybrid_search_rrf(
            dense_vector=BETA_QUERY_DENSE,
            sparse_vector=BETA_QUERY_SPARSE,
            top_k=5,
            return_meta=True,
        )
        assert meta["backend_error"] is False, meta
        assert results[0]["id"] == BETA_POINT_ID
        assert results[0]["text"] == BETA_TEXT
        assert results[0]["metadata"]["doc_id"] == BETA_DOC_ID
    finally:
        await service.close()


# ---------------------------------------------------------------------------
# Scenario 5 — production ColBERT path proves ColBERT was actually applied
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_production_colbert_search_applies_maxsim_and_returns_expected_top1(
    harness_env: LiveE2EEnv, owned_collection: QdrantTestContext
) -> None:
    """hybrid_search_rrf_colbert reranks server-side and reports it truthfully."""
    _upsert_gate_points(harness_env, owned_collection.collection_name)
    service = _production_service(harness_env, owned_collection.collection_name)
    try:
        results, meta = await service.hybrid_search_rrf_colbert(
            dense_vector=ALPHA_QUERY_DENSE,
            colbert_query=ALPHA_QUERY_COLBERT,
            sparse_vector=ALPHA_QUERY_SPARSE,
            top_k=5,
            return_meta=True,
        )
        # #3461 meta contract: a non-empty result after this call means ColBERT
        # MaxSim reranking produced the ordering — no fallback happened.
        assert meta["backend_error"] is False, meta
        assert meta["colbert_applied"] is True, meta
        assert "fallback_reason" not in meta, meta
        assert results[0]["id"] == ALPHA_POINT_ID
        assert results[0]["text"] == ALPHA_TEXT
        assert results[0]["metadata"]["doc_id"] == ALPHA_DOC_ID
        # Two perfect query-token matches: MaxSim sums to exactly 2.0. An RRF
        # fallback could never produce this score, so the number itself proves
        # the multivector path executed.
        assert results[0]["score"] == pytest.approx(2.0)

        results, meta = await service.hybrid_search_rrf_colbert(
            dense_vector=BETA_QUERY_DENSE,
            colbert_query=BETA_QUERY_COLBERT,
            sparse_vector=BETA_QUERY_SPARSE,
            top_k=5,
            return_meta=True,
        )
        assert meta["colbert_applied"] is True and meta["backend_error"] is False, meta
        assert results[0]["id"] == BETA_POINT_ID
        assert results[0]["text"] == BETA_TEXT
        assert results[0]["score"] == pytest.approx(2.0)
    finally:
        await service.close()


# ---------------------------------------------------------------------------
# Scenario 6 — missing collection and incompatible schema are non-successes
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_missing_collection_and_incompatible_schema_fail_without_green(
    harness_env: LiveE2EEnv, owned_registry: TeardownRegistry, run_namespace: RunNamespace
) -> None:
    """A listening-but-unusable Qdrant cannot produce a passing gate."""
    # Missing collection: ensure_collection refuses with an actionable error.
    missing_name = generate_collection_name(run_namespace.run_id, run_namespace.worker)
    missing_service = _production_service(harness_env, missing_name)
    try:
        with pytest.raises(RuntimeError, match="not found"):
            await missing_service.hybrid_search_rrf(
                dense_vector=ALPHA_QUERY_DENSE, top_k=5, return_meta=True
            )
        with pytest.raises(RuntimeError, match="not found"):
            await missing_service.hybrid_search_rrf_colbert(
                dense_vector=ALPHA_QUERY_DENSE,
                colbert_query=ALPHA_QUERY_COLBERT,
                top_k=5,
                return_meta=True,
            )
    finally:
        await missing_service.close()

    # Schema-incompatible collection: the named-vector queries must surface
    # actionable per-call failure meta, never an empty-looking success.
    incompatible_name = generate_collection_name(run_namespace.run_id, run_namespace.worker)
    owned_registry.register_collection(harness_env.qdrant_url, incompatible_name)
    client = _client(harness_env)
    try:
        client.create_collection(
            collection_name=incompatible_name,
            vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE),
        )
    finally:
        client.close()

    incompatible_service = _production_service(harness_env, incompatible_name)
    try:
        results, meta = await incompatible_service.hybrid_search_rrf(
            dense_vector=ALPHA_QUERY_DENSE,
            sparse_vector=ALPHA_QUERY_SPARSE,
            top_k=5,
            return_meta=True,
        )
        assert results == []
        assert meta["backend_error"] is True, meta
        assert meta["error_type"], meta
        assert meta["error_message"], "the failure meta must carry an actionable message"

        colbert_results, colbert_meta = await incompatible_service.hybrid_search_rrf_colbert(
            dense_vector=ALPHA_QUERY_DENSE,
            colbert_query=ALPHA_QUERY_COLBERT,
            sparse_vector=ALPHA_QUERY_SPARSE,
            top_k=5,
            return_meta=True,
        )
        assert colbert_results == []
        assert colbert_meta["backend_error"] is True, colbert_meta
        assert colbert_meta["colbert_applied"] is False, colbert_meta
        assert colbert_meta["fallback_reason"] == "colbert_unavailable", colbert_meta
    finally:
        await incompatible_service.close()


# ---------------------------------------------------------------------------
# Scenario 7 — opt-in isolated restart-persistence proof
#
# Destructive by nature (restarts a container), so the case exists only when
# explicitly selected: QDRANT_E2E_RESTART_PROJECT must name an exactly-supplied
# disposable harness Compose project (rag-e2e-<12-hex>, #3414 convention).
# Anything else is refused BEFORE any docker command runs.
# ---------------------------------------------------------------------------

_RESTART_PROJECT = os.getenv("QDRANT_E2E_RESTART_PROJECT", "").strip()

if _RESTART_PROJECT:  # pragma: no cover - exercised only in the opt-in lane

    def _docker(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )

    def _restart_target_container(project: str) -> str:
        """The single qdrant container of the disposable project, or a refusal."""
        listed = _docker(
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={_QDRANT_COMPOSE_SERVICE}",
            "--format",
            "{{.ID}} {{.Names}}",
        )
        if listed.returncode != 0:
            pytest.fail(f"docker ps failed: {listed.stderr.strip()}")
        containers = listed.stdout.splitlines()
        if len(containers) != 1:
            pytest.fail(
                f"refusing to restart: expected exactly one "
                f"{_QDRANT_COMPOSE_SERVICE!r} container in Compose project "
                f"{project!r}, found {len(containers)}: {containers}"
            )
        return containers[0].split()[0]

    def _wait_for_readiness(env: LiveE2EEnv, deadline_s: float) -> None:
        """Bounded /readyz polling — never an arbitrary sleep."""
        deadline = time.monotonic() + deadline_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(f"{env.qdrant_url.rstrip('/')}/readyz")
                    response.raise_for_status()
                return
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
        raise RuntimeError(f"Qdrant not ready within {deadline_s}s after restart: {last_error!r}")

    def _wait_for_collection(
        harness_env: LiveE2EEnv, collection_name: str, deadline_s: float
    ) -> int:
        """Bounded count polling until the recovered collection answers."""
        deadline = time.monotonic() + deadline_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                client = _client(harness_env, timeout=10)
                try:
                    return client.count(collection_name=collection_name).count
                finally:
                    client.close()
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
        raise RuntimeError(
            f"collection {collection_name!r} did not recover within {deadline_s}s "
            f"after restart: {last_error!r}"
        )

    @pytest.mark.timeout(300)
    @pytest.mark.asyncio
    async def test_qdrant_survives_controlled_container_restart(
        harness_env: LiveE2EEnv,
        owned_collection: QdrantTestContext,
    ) -> None:
        """Count and both production search results survive a controlled restart."""
        # Refuse anything that is not the explicitly supplied disposable
        # harness project — before any docker interaction.
        if not _DISPOSABLE_PROJECT_RE.match(_RESTART_PROJECT):
            pytest.fail(
                f"QDRANT_E2E_RESTART_PROJECT={_RESTART_PROJECT!r} is not a disposable "
                "harness Compose project ('rag-e2e-<12-hex>' per #3414 "
                "compose_project_name); refusing to restart"
            )
        container_id = _restart_target_container(_RESTART_PROJECT)

        _upsert_gate_points(harness_env, owned_collection.collection_name)
        collection_name = owned_collection.collection_name

        # Baseline through the production service.
        baseline = _production_service(harness_env, collection_name)
        try:
            rrf_baseline, rrf_meta = await baseline.hybrid_search_rrf(
                dense_vector=ALPHA_QUERY_DENSE,
                sparse_vector=ALPHA_QUERY_SPARSE,
                top_k=5,
                return_meta=True,
            )
            colbert_baseline, colbert_meta = await baseline.hybrid_search_rrf_colbert(
                dense_vector=ALPHA_QUERY_DENSE,
                colbert_query=ALPHA_QUERY_COLBERT,
                sparse_vector=ALPHA_QUERY_SPARSE,
                top_k=5,
                return_meta=True,
            )
        finally:
            await baseline.close()
        assert rrf_meta["backend_error"] is False and colbert_meta["backend_error"] is False
        assert rrf_baseline[0]["id"] == ALPHA_POINT_ID
        assert colbert_baseline[0]["id"] == ALPHA_POINT_ID
        assert colbert_meta["colbert_applied"] is True

        # Controlled restart of the exact run-owned project's container.
        restarted = _docker("restart", container_id, timeout=180.0)
        if restarted.returncode != 0:
            pytest.fail(f"docker restart {container_id} failed: {restarted.stderr.strip()}")

        # Bounded readiness: /readyz first, then the recovered collection.
        _wait_for_readiness(harness_env, _READINESS_DEADLINE_S)
        recovered_count = _wait_for_collection(harness_env, collection_name, _READINESS_DEADLINE_S)
        assert recovered_count == 2, f"expected 2/2 points after restart, got {recovered_count}"

        # Fresh service instances prove the data — not a cached connection.
        recovered = _production_service(harness_env, collection_name)
        try:
            rrf_after, rrf_meta_after = await recovered.hybrid_search_rrf(
                dense_vector=ALPHA_QUERY_DENSE,
                sparse_vector=ALPHA_QUERY_SPARSE,
                top_k=5,
                return_meta=True,
            )
            colbert_after, colbert_meta_after = await recovered.hybrid_search_rrf_colbert(
                dense_vector=ALPHA_QUERY_DENSE,
                colbert_query=ALPHA_QUERY_COLBERT,
                sparse_vector=ALPHA_QUERY_SPARSE,
                top_k=5,
                return_meta=True,
            )
        finally:
            await recovered.close()
        assert rrf_meta_after["backend_error"] is False, rrf_meta_after
        assert [result["id"] for result in rrf_after] == [
            result["id"] for result in rrf_baseline
        ], "RRF ranking must be unchanged after restart"
        assert rrf_after[0]["id"] == ALPHA_POINT_ID
        assert rrf_after[0]["text"] == ALPHA_TEXT
        assert colbert_meta_after["backend_error"] is False, colbert_meta_after
        assert colbert_meta_after["colbert_applied"] is True, colbert_meta_after
        assert colbert_after[0]["id"] == colbert_baseline[0]["id"] == ALPHA_POINT_ID
        assert colbert_after[0]["text"] == ALPHA_TEXT
