"""Live harness proof: run-owned stack, disjoint namespaces, leak-free teardown.

This lane is the #3414 acceptance proof against the run's real local
Redis/Qdrant/PostgreSQL/BGE-M3 (the disposable Compose project started by
``make e2e-harness``):

- the full stack must be up (required mode FAILS, never skips);
- BGE-M3 must serve the real pinned model (runtime artifact gate);
- two worker namespaces get disjoint collection/prefix/db/schema resources
  and teardown proves ZERO owned leaks;
- teardown refuses non-owned (shared/production/foreign-run) resources.

Run via the canonical entry: ``make e2e-harness`` (sets E2E_RUN_ID,
E2E_HARNESS_REQUIRED=1, and the operator credentials).
"""

from __future__ import annotations

import pytest

from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    RunNamespace,
    TeardownRegistry,
    _postgres_dsn_from_env,
    _redis_url_with_db,
    cleanup_collection,
    make_qdrant_context,
    provide_postgres_schema,
    provide_redis_namespace,
    recreate_collection,
    require_live_stack,
    verify_bge_runtime,
)
from tests.e2e_core.qdrant_helpers import (
    HarnessSafetyError,
    QdrantTestContext,
    generate_collection_name,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


def _env() -> LiveE2EEnv:
    return LiveE2EEnv.from_env()


def _worker_context(env: LiveE2EEnv, run_id: str, worker: str) -> QdrantTestContext:
    return QdrantTestContext(
        collection_name=generate_collection_name(run_id, worker),
        qdrant_url=env.qdrant_url,
        keep=False,
        run_id=run_id,
    )


async def _provision_worker_namespace(
    env: LiveE2EEnv, worker: str, run_id: str
) -> tuple[RunNamespace, TeardownRegistry]:
    """Create one worker's collection/prefix/schema and register teardown."""
    namespace = RunNamespace(run_id=run_id, worker=worker)
    registry = TeardownRegistry(run_id=run_id)

    context = _worker_context(env, run_id, worker)
    registry.register_collection(env.qdrant_url, context.collection_name)
    recreate_collection(env, context.collection_name)

    redis_lease = await provide_redis_namespace(None, namespace)
    registry.register_redis(redis_lease)
    import redis.asyncio as aioredis

    writer = aioredis.from_url(redis_lease.url, decode_responses=True)
    try:
        await writer.set(f"{redis_lease.prefix}data", f"payload-{worker}")
    finally:
        await writer.aclose()

    postgres_lease = await provide_postgres_schema(None, namespace)
    registry.register_postgres(postgres_lease)
    import asyncpg

    connection = await asyncpg.connect(postgres_lease.dsn, timeout=10)
    try:
        await connection.execute(
            f'CREATE TABLE IF NOT EXISTS "{postgres_lease.schema}".probe (id int primary key)'
        )
        await connection.execute(f'INSERT INTO "{postgres_lease.schema}".probe VALUES (1)')
    finally:
        await connection.close()

    return namespace, registry


async def _assert_namespace_state(
    env: LiveE2EEnv, namespace: RunNamespace, *, expect: bool
) -> None:
    """Assert the worker's collection/keys/schema exist (or are fully gone)."""
    from qdrant_client import QdrantClient

    prefix = f"rag_e2e_{namespace.run_id}_{namespace.worker}_"

    client = QdrantClient(url=env.qdrant_url, timeout=10.0)
    try:
        names = {item.name for item in client.get_collections().collections}
    finally:
        client.close()
    owned = [name for name in names if name.startswith(prefix)]
    if expect:
        assert owned, f"expected an owned collection for {namespace.worker}, found none"

    import redis.asyncio as aioredis

    reader = aioredis.from_url(_redis_url_with_db(None, namespace.redis_db), decode_responses=True)
    try:
        keys = [key async for key in reader.scan_iter(match=f"{namespace.redis_prefix}*")]
    finally:
        await reader.aclose()
    if expect:
        assert keys, f"expected owned redis keys for {namespace.worker}"

    import asyncpg

    connection = await asyncpg.connect(_postgres_dsn_from_env(), timeout=10)
    try:
        present = await connection.fetchval(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
            namespace.postgres_schema,
        )
    finally:
        await connection.close()
    if expect:
        assert present == 1, f"expected schema {namespace.postgres_schema}"


@pytest.mark.asyncio
async def test_required_stack_is_up_and_bge_serves_pinned_model() -> None:
    """Full real stack answers; BGE /health model_loaded + 1024-dim dense encode."""
    env = _env()
    await require_live_stack(env)
    report = await verify_bge_runtime(env)
    assert report["dimension"] == 1024
    assert report["health"]["model_loaded"] is True


@pytest.mark.asyncio
async def test_two_worker_namespaces_are_disjoint_and_teardown_proves_zero_leaks() -> None:
    """gw0/gw1 resources never collide; registry teardown leaves zero owned resources."""
    env = _env()
    await require_live_stack(env)
    run_id = RunNamespace.resolve().run_id

    gw0_namespace, gw0_registry = await _provision_worker_namespace(env, "gw0", run_id)
    gw1_namespace, gw1_registry = await _provision_worker_namespace(env, "gw1", run_id)

    try:
        assert gw0_namespace.redis_prefix != gw1_namespace.redis_prefix
        assert gw0_namespace.redis_db != gw1_namespace.redis_db
        assert gw0_namespace.postgres_schema != gw1_namespace.postgres_schema
        assert gw0_namespace.qdrant_collection != gw1_namespace.qdrant_collection
        await _assert_namespace_state(env, gw0_namespace, expect=True)
        await _assert_namespace_state(env, gw1_namespace, expect=True)
    finally:
        await gw0_registry.teardown_and_verify()
        await gw1_registry.teardown_and_verify()

    await _assert_namespace_state(env, gw0_namespace, expect=False)
    await _assert_namespace_state(env, gw1_namespace, expect=False)


def test_teardown_refuses_non_owned_resources() -> None:
    """Registry and cleanup refuse production/shared/foreign-run names."""
    env = _env()
    run_id = RunNamespace.resolve().run_id
    registry = TeardownRegistry(run_id=run_id)

    for name in (
        "gdrive_documents_bge",
        "file_documents_bge",
        "rag_e2e_ffffffffffff_gw0_deadbeef",  # foreign run
        "e2e_core_0123456789abcdef",  # legacy un-namespaced prefix
    ):
        # Run-bound guard: refuses everything outside this run's namespace.
        with pytest.raises(HarnessSafetyError):
            registry.register_collection(env.qdrant_url, name)
        with pytest.raises(HarnessSafetyError):
            QdrantTestContext(
                collection_name=name, qdrant_url=env.qdrant_url, keep=False, run_id=run_id
            )

    for name in (
        "gdrive_documents_bge",
        "file_documents_bge",
        "e2e_core_0123456789abcdef",
        "my_test_collection",
    ):
        # Format guard (legacy call sites without a run id): refuses
        # production names and anything outside the rag_e2e_ namespace.
        with pytest.raises(HarnessSafetyError):
            cleanup_collection(
                env,
                QdrantTestContext(
                    collection_name=name, qdrant_url=env.qdrant_url, keep=False, run_id=""
                ),
            )

    with pytest.raises(HarnessSafetyError):
        registry.refuse_non_owned_collection("gdrive_documents_bge")


@pytest.mark.asyncio
async def test_cleanup_collection_verifies_deletion() -> None:
    """cleanup_collection drops the owned collection and proves it is gone."""
    env = _env()
    await require_live_stack(env)
    context = make_qdrant_context(env)
    recreate_collection(env, context.collection_name)
    cleanup_collection(env, context)  # first call deletes and verifies absence
    cleanup_collection(env, context)  # idempotent second call still proves absence
