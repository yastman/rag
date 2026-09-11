"""Unit tests for scripts/demo_bootstrap.py — idempotent demo setup (#3202)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import scripts.demo_bootstrap as db
from src.runtime.qdrant import contracts
from src.runtime.qdrant.readiness import (
    CollectionReadiness,
    knowledge_demo_point_id,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _schema_obj(type_name: str) -> SimpleNamespace:
    return SimpleNamespace(data_type=SimpleNamespace(value=type_name))


def _contract_schema(role: str) -> dict:
    from src.runtime.qdrant.readiness import apartments_contract, knowledge_contract

    contract = apartments_contract() if role == "apartments" else knowledge_contract("k")
    return {i.field_name: _schema_obj(i.schema_type) for i in contract.payload_indexes}


def _info(
    points: int = 0,
    role: str = "knowledge",
    dense: tuple[str, ...] = ("dense", "colbert"),
    sparse: tuple[str, ...] = ("bm42",),
) -> SimpleNamespace:
    return SimpleNamespace(
        points_count=points,
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={name: SimpleNamespace(size=1024) for name in dense},
                sparse_vectors={name: SimpleNamespace() for name in sparse},
            )
        ),
        payload_schema=_contract_schema(role),
    )


class _FakeAsyncClient:
    """Async client double: contract-ready collections holding demo points."""

    def __init__(self, shipped_points: bool = True) -> None:
        self._shipped_points = shipped_points

    async def collection_exists(self, collection: str) -> bool:
        return True

    async def get_collection(self, collection: str) -> SimpleNamespace:
        role = "apartments" if "apartments" in collection else "knowledge"
        return _info(points=3, role=role)

    async def count(self, collection_name: str, count_filter=None, exact: bool = False):
        for cond in count_filter.must or []:
            has_id = getattr(cond, "has_id", None)
            if has_id is not None:
                present = len(has_id) if self._shipped_points else 0
                return SimpleNamespace(count=present)
            if getattr(cond, "range", None) is not None:
                return SimpleNamespace(count=0)  # intentional no-result probe
        return SimpleNamespace(count=2)  # shipped-row probes match

    async def close(self) -> None:
        return None


async def _fake_validate(client, contract, run_probes=False, probes=None):
    """Validate double: always contract-ready, records expect-results probe names."""
    readiness = CollectionReadiness(collection=contract.collection_name, role=contract.role)
    readiness.points_count = 3
    if run_probes and probes:
        readiness.probe_results = {p.name: 1 for p in probes if p.expect_results}
    return readiness


def _ready_readiness(name: str) -> CollectionReadiness:
    readiness = CollectionReadiness(collection=name, role="verify")
    readiness.points_count = 3
    return readiness


# ---------------------------------------------------------------------------
# Schema guard
# ---------------------------------------------------------------------------


class TestSchemaCompatible:
    def test_contract_schema_is_compatible(self):
        assert db._schema_compatible(_info()) is True

    def test_missing_bm42_is_incompatible(self):
        assert db._schema_compatible(_info(sparse=())) is False

    def test_missing_dense_is_incompatible(self):
        assert db._schema_compatible(_info(dense=())) is False


# ---------------------------------------------------------------------------
# Explicit bootstrap mutations (strict mode owned by setup, not reads — #3333)
# ---------------------------------------------------------------------------


class TestExplicitBootstrapMutations:
    def test_knowledge_schema_creation_applies_strict_mode(self):
        client = MagicMock()
        db.create_knowledge_collection_schema(client, "i3202-knowledge")
        client.update_collection.assert_called_once_with(
            collection_name="i3202-knowledge",
            strict_mode_config=contracts.strict_mode_config(),
        )

    def test_apartments_schema_creation_applies_strict_mode(self):
        client = MagicMock()
        db.create_apartments_collection_schema(client, "i3202-apartments")
        client.update_collection.assert_called_once_with(
            collection_name="i3202-apartments",
            strict_mode_config=contracts.strict_mode_config(),
        )


# ---------------------------------------------------------------------------
# Knowledge demo ingest
# ---------------------------------------------------------------------------


class TestIngestKnowledgeDemo:
    def _write_corpus(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "article_115.md").write_text(
            "# Особлива частина\n\n## Злочини проти життя та здоров'я особи\n\n"
            "### Стаття 115. Умисне вбивство\n\nумисне вбивство\n",
            encoding="utf-8",
        )
        (corpus / "article_185.md").write_text(
            "# Особлива частина\n\n## Злочини проти власності\n\n"
            "### Стаття 185. Крадіжка\n\nкрадіжка\n",
            encoding="utf-8",
        )
        return corpus

    def test_upserts_deterministic_ids_with_metadata_contract(self, tmp_path):
        corpus = self._write_corpus(tmp_path)
        client = MagicMock()
        hybrid = SimpleNamespace(
            dense_vecs=[[0.1] * 1024, [0.2] * 1024],
            lexical_weights=[{"indices": [1], "values": [0.5]}] * 2,
            colbert_vecs=None,
        )
        fake_bge = MagicMock()
        fake_bge.encode_hybrid.return_value = hybrid

        with patch("src.services.bge_m3_client.BGEM3SyncClient", return_value=fake_bge):
            count = db.ingest_knowledge_demo(client, "i3202-knowledge", corpus, "http://bge")

        assert count == 2
        fake_bge.encode_hybrid.assert_called_once()
        fake_bge.close.assert_called_once()
        call_kwargs = client.upsert.call_args[1]
        assert call_kwargs["collection_name"] == "i3202-knowledge"
        assert call_kwargs["wait"] is True
        points = call_kwargs["points"]
        assert [str(p.id) for p in points] == [
            knowledge_demo_point_id("article_115"),
            knowledge_demo_point_id("article_185"),
        ]
        # metadata.doc_id is the canonical indexed knowledge identifier (#3333);
        # the unindexed metadata.id alias is gone.
        assert points[0].payload["metadata"]["doc_id"] == "article_115"
        assert points[0].payload["metadata"]["title"] == "Стаття 115. Умисне вбивство"
        assert "id" not in points[0].payload["metadata"]
        assert "page_content" in points[0].payload
        assert "dense" in points[0].vector and "bm42" in points[0].vector
        # The production Markdown parser owns the shipped text: the heading
        # context line is prepended exactly as in unified ingestion (#3235).
        assert points[0].payload["page_content"] == (
            "Особлива частина > Злочини проти життя та здоров'я особи"
            " > Стаття 115. Умисне вбивство\nумисне вбивство"
        )

    def test_empty_corpus_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError, match="empty"):
            db.ingest_knowledge_demo(MagicMock(), "k", empty, "http://bge")

    def test_non_markdown_files_in_corpus_dir_are_ignored(self, tmp_path):
        corpus = self._write_corpus(tmp_path)
        (corpus / "article_999.json").write_text("{}", encoding="utf-8")
        fake_bge = MagicMock()
        fake_bge.encode_hybrid.return_value = SimpleNamespace(
            dense_vecs=[[0.1] * 1024, [0.2] * 1024],
            lexical_weights=[{"indices": [1], "values": [0.5]}] * 2,
            colbert_vecs=None,
        )
        with patch("src.services.bge_m3_client.BGEM3SyncClient", return_value=fake_bge):
            count = db.ingest_knowledge_demo(MagicMock(), "k", corpus, "http://bge")
        assert count == 2  # the .json file is ignored, never parsed

    def test_multi_chunk_document_is_rejected(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "article_115.md").write_text(
            "# T\n\n" + ("paragraph text\n\n" * 700), encoding="utf-8"
        )
        with patch("src.services.bge_m3_client.BGEM3SyncClient"):
            with pytest.raises(ValueError, match="exactly one chunk"):
                db.ingest_knowledge_demo(MagicMock(), "k", corpus, "http://bge")


# ---------------------------------------------------------------------------
# Apartments demo ingest
# ---------------------------------------------------------------------------


class TestIngestApartmentsDemo:
    def test_delegates_to_incremental_runner_full_mode(self):
        runner = MagicMock()
        runner.run_incremental.return_value = {"total": 2, "changed": 2}

        with patch(
            "src.ingestion.apartments.runner.IncrementalApartmentIngester",
            return_value=runner,
        ) as factory:
            stats = db.ingest_apartments_demo(
                "data/apartments.csv",
                "http://localhost:6333",
                "http://localhost:8000",
                state_path=".state.json",
                collection_name="audit_3460_apartments",
                qdrant_api_key="test-api-key-3460",
            )

        assert stats == {"total": 2, "changed": 2}
        assert factory.call_args.kwargs["state_path"] == ".state.json"
        assert factory.call_args.kwargs["collection_name"] == "audit_3460_apartments"
        assert factory.call_args.kwargs["qdrant_api_key"] == "test-api-key-3460"
        runner.run_incremental.assert_called_once_with(force_full=True)


# ---------------------------------------------------------------------------
# Verify orchestration
# ---------------------------------------------------------------------------


class TestVerifyReady:
    async def test_probes_enforced_when_shipped_demo_data_present(self, args=None):
        namespace = SimpleNamespace(
            knowledge_collection="i3202-knowledge",
            apartments_collection="i3202-apartments",
            apartments_csv="data/apartments.csv",
            qdrant_url="http://localhost:6333",
            qdrant_api_key=None,
        )
        with (
            patch("qdrant_client.AsyncQdrantClient", return_value=_FakeAsyncClient()),
            patch.object(db, "validate_collection", _fake_validate),
        ):
            readiness = await db.verify_ready(namespace)

        assert [item.ok for item in readiness] == [True, True]
        knowledge_probes = readiness[0].probe_results
        assert "demo-corpus:article_115" in knowledge_probes
        apartments_probes = readiness[1].probe_results
        # One probe per distinct advertised shape, not per row (#3333).
        assert any(name.startswith("shipped-shape:") for name in apartments_probes)
        assert (
            apartments_probes.get("intentional-no-result") is None
        )  # no-result probe is expect_results=False
        assert all(count >= 1 for name, count in apartments_probes.items())

    async def test_probes_skipped_for_populated_environment(self):
        namespace = SimpleNamespace(
            knowledge_collection="i3202-knowledge",
            apartments_collection="i3202-apartments",
            apartments_csv="data/apartments.csv",
            qdrant_url="http://localhost:6333",
            qdrant_api_key=None,
        )
        with (
            patch(
                "qdrant_client.AsyncQdrantClient",
                return_value=_FakeAsyncClient(shipped_points=False),
            ),
            patch.object(db, "validate_collection", _fake_validate),
        ):
            readiness = await db.verify_ready(namespace)

        assert [item.ok for item in readiness] == [True, True]
        for item in readiness:
            enforced = [
                name
                for name in item.probe_results
                if name.startswith(("demo-corpus", "shipped-shape"))
            ]
            assert enforced == []

    async def test_verify_uses_selected_collection_and_supplied_api_key(self):
        """#3460 pin: readiness counts target the selected collection with the
        supplied credentials (auth + collection isolation on the verify path)."""
        namespace = SimpleNamespace(
            knowledge_collection="i3202-knowledge",
            apartments_collection="audit_3460_apartments",
            apartments_csv="data/apartments.csv",
            qdrant_url="https://qdrant.example",
            qdrant_api_key="test-api-key-3460",
        )
        with (
            patch("qdrant_client.AsyncQdrantClient") as MockAsync,
            patch.object(db, "validate_collection", _fake_validate),
        ):
            client = MockAsync.return_value
            client.count = AsyncMock(return_value=SimpleNamespace(count=0))
            client.close = AsyncMock()
            await db.verify_ready(namespace)

        MockAsync.assert_called_once_with(url="https://qdrant.example", api_key="test-api-key-3460")
        count_targets = {c.kwargs["collection_name"] for c in client.count.call_args_list}
        assert count_targets == {"i3202-knowledge", "audit_3460_apartments"}


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def _argv(self, extra: list[str] | None = None) -> list[str]:
        return [
            "--knowledge-collection",
            "i3202-knowledge",
            "--apartments-collection",
            "i3202-apartments",
            "--apartments-csv",
            "data/apartments.csv",
            *(extra or []),
        ]

    def test_verify_only_passes_when_collections_ready(self):
        results = [_ready_readiness("i3202-knowledge"), _ready_readiness("i3202-apartments")]
        with patch.object(db, "verify_ready", AsyncMock(return_value=results)):
            code = db.main(self._argv(["--verify-only"]))
        assert code == 0

    def test_verify_only_fails_with_actionable_errors(self):
        failed = CollectionReadiness(collection="i3202-apartments", role="apartments")
        failed.fail("missing", "collection does not exist")
        results = [_ready_readiness("i3202-knowledge"), failed]
        with patch.object(db, "verify_ready", AsyncMock(return_value=results)):
            code = db.main(self._argv(["--verify-only"]))
        assert code == 1

    def test_fresh_bootstrap_creates_both_collections(self, tmp_path):
        """Fresh case: nothing exists → schemas created and demo ingest runs."""
        client = MagicMock()
        client.get_collection.side_effect = [None, None, None, None]
        results = [_ready_readiness("i3202-knowledge"), _ready_readiness("i3202-apartments")]
        with (
            patch.object(db, "QdrantClient", return_value=client),
            patch.object(db, "verify_ready", AsyncMock(return_value=results)),
            patch.object(db, "create_knowledge_collection_schema") as create_k,
            patch.object(db, "create_apartments_collection_schema") as create_a,
            patch.object(db, "ingest_knowledge_demo", return_value=1) as ingest_k,
            patch.object(db, "ingest_apartments_demo", return_value={}) as ingest_a,
        ):
            code = db.main(self._argv())

        assert code == 0
        create_k.assert_called_once()
        create_a.assert_called_once()
        ingest_k.assert_called_once()
        ingest_a.assert_called_once()

    def test_fresh_bootstrap_passes_selected_collection_and_api_key_to_ingest(self):
        """#3460 regression: the selected isolated collection and the supplied
        Qdrant credentials must reach the writer, not just the schema check."""
        client = MagicMock()
        client.get_collection.side_effect = [None, None, None, None]
        results = [
            _ready_readiness("i3202-knowledge"),
            _ready_readiness("audit_3460_apartments"),
        ]
        argv = [
            "--knowledge-collection",
            "i3202-knowledge",
            "--apartments-collection",
            "audit_3460_apartments",
            "--qdrant-api-key",
            "test-api-key-3460",
            "--apartments-csv",
            "data/apartments.csv",
        ]
        with (
            patch.object(db, "QdrantClient", return_value=client),
            patch.object(db, "verify_ready", AsyncMock(return_value=results)),
            patch.object(db, "create_knowledge_collection_schema"),
            patch.object(db, "create_apartments_collection_schema"),
            patch.object(db, "ingest_knowledge_demo"),
            patch.object(db, "ingest_apartments_demo", return_value={}) as ingest_a,
        ):
            code = db.main(argv)

        assert code == 0
        assert ingest_a.call_args.kwargs["collection_name"] == "audit_3460_apartments"
        assert ingest_a.call_args.kwargs["qdrant_api_key"] == "test-api-key-3460"

    def test_populated_bootstrap_preserves_data(self):
        """Populated-upgrade case: populated collections are left untouched."""
        client = MagicMock()
        client.get_collection.side_effect = [
            _info(points=120, role="knowledge"),
            _info(points=450, role="apartments"),
        ]
        results = [_ready_readiness("i3202-knowledge"), _ready_readiness("i3202-apartments")]
        with (
            patch.object(db, "QdrantClient", return_value=client),
            patch.object(db, "verify_ready", AsyncMock(return_value=results)),
            patch.object(db, "create_knowledge_collection_schema") as create_k,
            patch.object(db, "create_apartments_collection_schema") as create_a,
            patch.object(db, "ingest_knowledge_demo") as ingest_k,
            patch.object(db, "ingest_apartments_demo") as ingest_a,
        ):
            code = db.main(self._argv())

        assert code == 0
        create_k.assert_not_called()
        create_a.assert_not_called()
        ingest_k.assert_not_called()
        ingest_a.assert_not_called()

    def test_incompatible_schema_is_reported_not_touched(self):
        client = MagicMock()
        client.get_collection.side_effect = [
            _info(points=0, dense=("dense",), sparse=()),  # knowledge: no bm42
            _info(points=0, role="apartments"),
        ]
        results = [_ready_readiness("i3202-knowledge"), _ready_readiness("i3202-apartments")]
        with (
            patch.object(db, "QdrantClient", return_value=client),
            patch.object(db, "verify_ready", AsyncMock(return_value=results)),
            patch.object(db, "create_knowledge_collection_schema") as create_k,
            patch.object(db, "ingest_knowledge_demo") as ingest_k,
        ):
            code = db.main(self._argv())

        assert code == 1
        create_k.assert_not_called()
        ingest_k.assert_not_called()
