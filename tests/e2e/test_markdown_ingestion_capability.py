"""E2E capability: the Markdown CLI document lifecycle through retrieval (#3416).

One bounded scenario proving the production unified ingestion path end to end
(``run_once`` -> Markdown parser -> manifest -> BGE-M3 -> Qdrant writer)
against the hermetic harness stack (#3414): a run/worker-owned collection
with the production vector contract (harness ``recreate_collection``, the
same provisioning the harness lane uses), real Qdrant writes, real BGE-M3
embeddings, real dense retrieval.

Lifecycle proven (issue #3416 acceptance):

- only ``.md`` is indexed; every point carries complete dense+bm42+colbert;
- an unchanged second pass is a no-op; a completed pass retries idempotently;
- a changed file atomically replaces its generation with fresh payload identity;
- a changed-to-empty file deletes its stale points (#3370);
- a deleted file reconciles the manifest and leaves other sources untouched
  (run_once never sweeps vanished sources — removal is the sync layer's
  explicit job);
- a rename preserves file identity: in-place deterministic points, no churn,
  the old path stops being searchable (#3369);
- a copy keeps a distinct identity (#1603/#3369);
- an injected second-batch commit failure never exposes mixed generations
  (#1602): each file's replacement is ONE atomic request, so the second batch
  of the pass is the second file's commit — the failed source keeps its
  complete previous generation and the successful one is fully replaced;
  retry heals idempotently.

Redis is intentionally absent: production unified ingestion writes to Qdrant
through BGE-M3 only and consumes no Redis, so this lane performs no Redis
proof (#3416: no manual SET/GET).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from tests.e2e_core.live_harness import (
    LiveE2EEnv,
    RunNamespace,
    TeardownRegistry,
    make_qdrant_context,
    recreate_collection,
    require_live_services,
)
from tests.e2e_core.qdrant_helpers import production_collection_names


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]

# Sectioned Markdown bodies: sections are padded with natural repeated words
# so the tokenizer stays compact, and the ingest config uses a small chunk
# budget — together these keep every file's atomic replacement generation far
# below the writer's 28MB single-request gate (#1602) with real CPU BGE-M3
# encode cost inside the per-test timeout.
_SECTION_WORDS = 120
_FILLER = [
    "content",
    "document",
    "section",
    "detail",
    "listing",
    "estate",
    "example",
    "property",
    "note",
    "summary",
    "description",
]


def _markdown_body(intro_sentence: str, sections: int = 2) -> str:
    """Build a sectioned Markdown document embedding one distinctive sentence."""
    parts = [f"# {intro_sentence}", "", intro_sentence, ""]
    for index in range(sections):
        filler = " ".join(_FILLER[i % len(_FILLER)] for i in range(_SECTION_WORDS))
        parts.append(f"## Section {index}")
        parts.append("")
        parts.append(filler)
        parts.append("")
    return "\n".join(parts)


_ALPHA_V1 = "The crimson falcon protocol governs the northern archive."
_ALPHA_V2 = "The obsidian meridian rewiring replaced every northern relay."
_ALPHA_FINAL = "The granite comet almanac closes the alpha chronicle."
_BETA_V1 = "The sapphire harbor ledger records every coastal shipment."
_DELTA_V1 = "The turquoise lamppost registry maps the eastern boulevard."
_EPSILON_V2 = "The violet compass dossier rewrites the eastern route."
_ZETA_V2 = "The amber jetty catalog indexes the western piers."


# ---------------------------------------------------------------------------
# Fixtures: run-owned namespace, sync/manifest dirs, production config
# ---------------------------------------------------------------------------


@pytest.fixture
def harness_env() -> LiveE2EEnv:
    return LiveE2EEnv.from_env()


@pytest.fixture
def run_namespace() -> RunNamespace:
    return RunNamespace.resolve()


@pytest.fixture
async def owned_context(harness_env: LiveE2EEnv, run_namespace: RunNamespace):
    """A run/worker-owned Qdrant collection with leak-proof teardown (#3414)."""
    context = make_qdrant_context(harness_env)
    registry = TeardownRegistry(run_id=run_namespace.run_id)
    registry.register_collection(harness_env.qdrant_url, context.collection_name)
    yield context
    # Deletes the exact owned collection and PROVES it is gone.
    await registry.teardown_and_verify()


@pytest.fixture
def sync_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "sync"
    directory.mkdir()
    return directory


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "run-manifest"
    yield directory
    # No manifest residue: the run-owned manifest lives in the tmp dir only.
    shutil.rmtree(directory, ignore_errors=True)
    assert not directory.exists(), "run-owned manifest dir must not survive teardown"


@pytest.fixture
def ingest_config(
    sync_dir: Path,
    manifest_dir: Path,
    owned_context,
    harness_env: LiveE2EEnv,
):
    """Production UnifiedConfig bound to the run-owned namespace."""
    from src.ingestion.unified.config import UnifiedConfig

    return UnifiedConfig(
        sync_dir=sync_dir,
        manifest_dir=manifest_dir,
        collection_name=owned_context.collection_name,
        qdrant_url=harness_env.qdrant_url,
        qdrant_api_key=harness_env.qdrant_api_key,
        bge_m3_url=harness_env.bge_m3_url,
        max_tokens_per_chunk=64,
    )


# ---------------------------------------------------------------------------
# Read-side helpers (all real Qdrant / real BGE-M3)
# ---------------------------------------------------------------------------


def _all_payloads(harness_env: LiveE2EEnv, collection_name: str) -> list[dict[str, Any]]:
    """Every payload in the collection (scroll pagination)."""
    client = QdrantClient(
        url=harness_env.qdrant_url, api_key=harness_env.qdrant_api_key, timeout=60
    )
    payloads: list[dict[str, Any]] = []
    try:
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                if record.payload:
                    payloads.append(dict(record.payload))
            if offset is None:
                return payloads
    finally:
        client.close()


def _scroll_source(
    harness_env: LiveE2EEnv,
    collection_name: str,
    source: str,
    *,
    with_vectors: bool,
    limit: int = 100,
) -> list[Any]:
    client = QdrantClient(
        url=harness_env.qdrant_url, api_key=harness_env.qdrant_api_key, timeout=60
    )
    try:
        records, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="metadata.source", match=MatchValue(value=source))]
            ),
            limit=limit,
            with_payload=False,
            with_vectors=with_vectors,
        )
        return records
    finally:
        client.close()


def _point_ids_for_source(harness_env: LiveE2EEnv, collection_name: str, source: str) -> set:
    return {
        record.id
        for record in _scroll_source(harness_env, collection_name, source, with_vectors=False)
    }


def _count_for_source(harness_env: LiveE2EEnv, collection_name: str, source: str) -> int:
    client = QdrantClient(
        url=harness_env.qdrant_url, api_key=harness_env.qdrant_api_key, timeout=60
    )
    try:
        return client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="metadata.source", match=MatchValue(value=source))]
            ),
        ).count
    finally:
        client.close()


def _dense_search(
    harness_env: LiveE2EEnv, collection_name: str, query: str, limit: int = 5
) -> list[tuple[str, float]]:
    """Real dense retrieval: BGE-M3 query embedding -> Qdrant query_points."""
    from src.services.bge_m3_client import BGEM3SyncClient

    encoder = BGEM3SyncClient(base_url=harness_env.bge_m3_url, timeout=120.0)
    try:
        dense = encoder.encode_dense([query]).vectors[0]
    finally:
        encoder.close()

    client = QdrantClient(
        url=harness_env.qdrant_url, api_key=harness_env.qdrant_api_key, timeout=60
    )
    try:
        response = client.query_points(
            collection_name=collection_name,
            query=dense,
            using="dense",
            limit=limit,
            with_payload=True,
        )
    finally:
        client.close()
    return [
        (point.payload["metadata"]["source"], point.score)  # type: ignore[index]
        for point in response.points
        if point.payload is not None
    ]


def _manifest_state(manifest_dir: Path) -> dict[str, Any]:
    manifest_path = manifest_dir / ".file_manifest.json"
    assert manifest_path.is_file(), "a run pass must persist the manifest"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "manifest must deserialize to a dict"
    return data


def _sources(payloads: list[dict[str, Any]]) -> set[str]:
    return {p["metadata"]["source"] for p in payloads}


def _file_ids_for(payloads: list[dict[str, Any]], source: str) -> set[str]:
    return {p["metadata"]["file_id"] for p in payloads if p["metadata"]["source"] == source}


def _content_hashes_for(payloads: list[dict[str, Any]], source: str) -> set[str]:
    return {p["metadata"]["content_hash"] for p in payloads if p["metadata"]["source"] == source}


# ---------------------------------------------------------------------------
# The lifecycle scenario
# ---------------------------------------------------------------------------


@pytest.mark.timeout(1200)
@pytest.mark.asyncio
async def test_markdown_cli_document_lifecycle_through_retrieval(
    harness_env: LiveE2EEnv,
    run_namespace: RunNamespace,
    owned_context,
    sync_dir: Path,
    manifest_dir: Path,
    ingest_config,
) -> None:
    """Ingest -> replace -> empty -> delete -> rename -> copy -> failure -> retry."""
    from src.ingestion.unified.flow import run_once

    await require_live_services(harness_env)

    # -- Phase 0: run-owned collection with the production vector contract ---
    # (dense 1024 + colbert multivector + bm42 sparse, per the harness helper;
    # production cmd_bootstrap's strict-mode guardrails currently reject
    # run_once's scroll page sizes — reported separately, #3459 evidence.)
    assert owned_context.collection_name.startswith(f"rag_e2e_{run_namespace.run_id}_")
    assert owned_context.collection_name not in production_collection_names()
    recreate_collection(harness_env, owned_context.collection_name)

    # -- Phase 1: ingest -> only .md indexed, vectors complete, retrievable -
    (sync_dir / "alpha.md").write_text(_markdown_body(_ALPHA_V1), encoding="utf-8")
    (sync_dir / "beta.md").write_text(_markdown_body(_BETA_V1, sections=1), encoding="utf-8")
    (sync_dir / "ignored.txt").write_text("not ingested", encoding="utf-8")

    first = run_once(ingest_config)
    assert first.processed == 2, f"expected the two .md files processed, got {first}"
    assert first.errors == 0, f"unexpected errors: {first.error_details}"

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    assert _sources(payloads) == {"alpha.md", "beta.md"}
    assert _count_for_source(harness_env, owned_context.collection_name, "ignored.txt") == 0
    assert all("not ingested" not in p["page_content"] for p in payloads)

    alpha_payloads = [p for p in payloads if p["metadata"]["source"] == "alpha.md"]
    assert len(alpha_payloads) >= 3, "sectioned document must yield multiple chunks"
    assert len(_content_hashes_for(payloads, "alpha.md")) == 1
    for payload in payloads:
        metadata = payload["metadata"]
        assert metadata["file_id"], "payload must carry file_id"
        assert metadata["content_hash"], "payload must carry content_hash"
        assert metadata["source_type"] == "file"
        assert metadata["source"] in {"alpha.md", "beta.md"}

    # dense + sparse + ColBERT complete on a live point (#3373 contract).
    records = _scroll_source(
        harness_env, owned_context.collection_name, "alpha.md", with_vectors=True, limit=1
    )
    vectors = dict(records[0].vector)
    assert set(vectors) == {"dense", "bm42", "colbert"}, (
        f"point must carry the complete named-vector set, got {sorted(vectors)}"
    )
    assert len(vectors["dense"]) == 1024
    sparse = vectors["bm42"]
    assert len(sparse.indices) > 0 and len(sparse.indices) == len(sparse.values)
    colbert = vectors["colbert"]
    assert len(colbert) > 0 and all(len(row) == 1024 for row in colbert)

    # Real retrieval: distinctive sentences find their own documents.
    assert _dense_search(harness_env, owned_context.collection_name, _ALPHA_V1)[0][0] == "alpha.md"
    assert _dense_search(harness_env, owned_context.collection_name, _BETA_V1)[0][0] == "beta.md"

    alpha_v1_hashes = _content_hashes_for(payloads, "alpha.md")

    # -- Phase 2: unchanged second pass is a no-op ---------------------------
    second = run_once(ingest_config)
    assert second.processed == 0, f"unchanged files must not re-index, got {second}"
    assert second.skipped == 2
    assert second.errors == 0

    # -- Phase 3: changed file atomically replaces with fresh identity -------
    (sync_dir / "alpha.md").write_text(_markdown_body(_ALPHA_V2), encoding="utf-8")
    third = run_once(ingest_config)
    assert third.processed == 1, f"only the changed file may re-index, got {third}"
    assert third.skipped == 1
    assert third.errors == 0

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    alpha_v2_hashes = _content_hashes_for(payloads, "alpha.md")
    assert alpha_v2_hashes.isdisjoint(alpha_v1_hashes), "old alpha content must be swept"
    assert len(alpha_v2_hashes) == 1
    assert len(_file_ids_for(payloads, "alpha.md")) == 1, "one file_id per generation"
    assert _dense_search(harness_env, owned_context.collection_name, _ALPHA_V2)[0][0] == "alpha.md"
    all_text = "\n".join(p["page_content"] for p in payloads)
    assert "crimson falcon protocol" not in all_text, (
        "replaced alpha generation must no longer be retrievable anywhere"
    )

    # -- Phase 4: changed-to-empty deletes stale points (#3370) --------------
    (sync_dir / "alpha.md").write_text("", encoding="utf-8")
    fourth = run_once(ingest_config)
    assert fourth.processed == 1, "empty replacement is processed, not skipped"
    assert fourth.errors == 0, f"unexpected errors: {fourth.error_details}"
    assert _count_for_source(harness_env, owned_context.collection_name, "alpha.md") == 0
    assert _count_for_source(harness_env, owned_context.collection_name, "beta.md") > 0

    # -- Phase 5: empty -> populated again (fresh generation) ----------------
    (sync_dir / "alpha.md").write_text(_markdown_body(_ALPHA_FINAL, sections=1), encoding="utf-8")
    fifth = run_once(ingest_config)
    assert fifth.processed == 1
    assert fifth.errors == 0
    assert _count_for_source(harness_env, owned_context.collection_name, "alpha.md") >= 1

    # -- Phase 6: deleted file reconciles the manifest, others untouched -----
    beta_points_before = _count_for_source(harness_env, owned_context.collection_name, "beta.md")
    (sync_dir / "beta.md").unlink()
    sixth = run_once(ingest_config)
    assert sixth.processed == 0
    assert sixth.skipped == 1
    assert sixth.errors == 0
    manifest = _manifest_state(manifest_dir)
    assert "beta.md" not in manifest["path_to_hash"], "deleted path must be reconciled"
    assert (
        _count_for_source(harness_env, owned_context.collection_name, "beta.md")
        == beta_points_before
    ), "run_once never sweeps vanished sources: points stay until the sync layer's explicit removal"

    # -- Phase 7: rename preserves identity (#3369) --------------------------
    (sync_dir / "delta.md").write_text(_markdown_body(_DELTA_V1, sections=1), encoding="utf-8")
    seventh = run_once(ingest_config)
    assert seventh.processed == 1
    assert seventh.errors == 0

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    delta_file_ids = _file_ids_for(payloads, "delta.md")
    assert len(delta_file_ids) == 1
    delta_file_id = next(iter(delta_file_ids))
    delta_point_ids = _point_ids_for_source(harness_env, owned_context.collection_name, "delta.md")

    (sync_dir / "delta.md").rename(sync_dir / "epsilon.md")
    eighth = run_once(ingest_config)
    assert eighth.processed == 1, "the renamed file must re-index under its new path"
    assert eighth.skipped == 1
    assert eighth.errors == 0

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    assert _sources(payloads) == {"alpha.md", "beta.md", "epsilon.md"}, (
        "delta.md points moved to epsilon.md; deleted beta.md points persist "
        "(run_once never sweeps vanished sources)"
    )
    assert _file_ids_for(payloads, "epsilon.md") == {delta_file_id}, (
        "rename must reuse the original file_id (identity preserved)"
    )
    assert (
        _point_ids_for_source(harness_env, owned_context.collection_name, "epsilon.md")
        == delta_point_ids
    ), "deterministic point ids: rename replaces in place, no churn"
    assert _count_for_source(harness_env, owned_context.collection_name, "delta.md") == 0
    manifest = _manifest_state(manifest_dir)
    assert "delta.md" not in manifest["path_to_hash"]
    assert manifest["hash_to_id"][manifest["path_to_hash"]["epsilon.md"]] == delta_file_id
    assert (
        _dense_search(harness_env, owned_context.collection_name, _DELTA_V1)[0][0] == "epsilon.md"
    )

    # -- Phase 8: copy stays distinct (#1603/#3369) --------------------------
    (sync_dir / "zeta.md").write_text(
        (sync_dir / "epsilon.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    pass_nine = run_once(ingest_config)
    assert pass_nine.processed == 1, "only the copy is new"
    assert pass_nine.skipped == 2
    assert pass_nine.errors == 0

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    epsilon_ids = _file_ids_for(payloads, "epsilon.md")
    zeta_ids = _file_ids_for(payloads, "zeta.md")
    assert len(epsilon_ids) == 1 and len(zeta_ids) == 1
    assert zeta_ids.isdisjoint(epsilon_ids), "a copy must receive its own file_id"
    epsilon_hashes = _content_hashes_for(payloads, "epsilon.md")
    zeta_hashes = _content_hashes_for(payloads, "zeta.md")
    assert epsilon_hashes == zeta_hashes, "copy shares bytes, so the same content_hash"
    manifest = _manifest_state(manifest_dir)
    content_hash = next(iter(epsilon_hashes))
    assert manifest["key_to_id"][f"epsilon.md:{content_hash}"] == delta_file_id
    assert manifest["key_to_id"][f"zeta.md:{content_hash}"] == next(iter(zeta_ids))

    # -- Phase 9: injected second-batch failure exposes no mixed generation --
    (sync_dir / "epsilon.md").write_text(_markdown_body(_EPSILON_V2, sections=1), encoding="utf-8")
    (sync_dir / "zeta.md").write_text(_markdown_body(_ZETA_V2, sections=1), encoding="utf-8")

    zeta_file_id = next(iter(zeta_ids))
    zeta_hashes_before = set(zeta_hashes)
    original_upsert = QdrantClient.upsert
    upsert_calls = {"count": 0}

    def failing_second_batch(self, *args: Any, **kwargs: Any):
        upsert_calls["count"] += 1
        if upsert_calls["count"] == 2:
            raise RuntimeError("injected second-batch commit failure (#3416)")
        return original_upsert(self, *args, **kwargs)

    QdrantClient.upsert = failing_second_batch  # type: ignore[method-assign]
    try:
        pass_ten = run_once(ingest_config)
    finally:
        QdrantClient.upsert = original_upsert  # type: ignore[method-assign]

    assert upsert_calls["count"] == 2, "both changed files must have attempted a commit"
    assert pass_ten.processed == 1, "epsilon's atomic commit succeeded"
    assert pass_ten.errors == 1
    assert any("zeta.md" in detail for detail in pass_ten.error_details)

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    # Successful replacement: fully new generation, single identity.
    assert _content_hashes_for(payloads, "epsilon.md").isdisjoint({content_hash})
    assert len(_file_ids_for(payloads, "epsilon.md")) == 1
    assert (
        _dense_search(harness_env, owned_context.collection_name, _EPSILON_V2)[0][0] == "epsilon.md"
    )
    # Failed replacement: complete previous generation, nothing mixed.
    assert _content_hashes_for(payloads, "zeta.md") == zeta_hashes_before
    assert _file_ids_for(payloads, "zeta.md") == {zeta_file_id}
    all_text = "\n".join(p["page_content"] for p in payloads)
    assert "amber jetty catalog" not in all_text, (
        "no point of the failed zeta replacement may be queryable"
    )
    assert "turquoise lamppost registry" in all_text, (
        "the failed source's complete last-good generation must remain"
    )
    hits = _dense_search(harness_env, owned_context.collection_name, _DELTA_V1, limit=10)
    assert any(source == "zeta.md" for source, _ in hits), (
        "the failed source's last-good generation must stay retrievable"
    )

    # -- Phase 10: retry after the fault is removed is idempotent ------------
    pass_eleven = run_once(ingest_config)
    assert pass_eleven.processed == 1, "the healed pass completes zeta's replacement"
    assert pass_eleven.errors == 0, f"unexpected errors: {pass_eleven.error_details}"

    payloads = _all_payloads(harness_env, owned_context.collection_name)
    zeta_now = _content_hashes_for(payloads, "zeta.md")
    assert zeta_now.isdisjoint(zeta_hashes_before), "old zeta generation swept on retry"
    assert len(zeta_now) == 1
    assert len(_file_ids_for(payloads, "zeta.md")) == 1
    assert _dense_search(harness_env, owned_context.collection_name, _ZETA_V2)[0][0] == "zeta.md"

    pass_twelve = run_once(ingest_config)
    assert pass_twelve.processed == 0, "a completed lifecycle must retry as a pure no-op"
    assert pass_twelve.skipped == 3
    assert pass_twelve.errors == 0
