"""Unit tests for src.runtime.qdrant.readiness — collection contracts (#3202)."""

import logging
from types import SimpleNamespace

import pytest
from qdrant_client.models import MatchAny, MatchValue, Range

from src.runtime.qdrant.readiness import (
    APARTMENTS_COLLECTION,
    BGEM3_DENSE_DIM,
    KIND_EMPTY,
    KIND_INSUFFICIENT_DATA,
    KIND_MISSING,
    KIND_PROBE_MISMATCH,
    KIND_SCHEMA_INCOMPATIBLE,
    KNOWLEDGE_DEMO_DOC_IDS,
    apartment_demo_point_id,
    apartment_demo_probes,
    apartments_contract,
    build_probe_filter,
    knowledge_contract,
    knowledge_demo_point_id,
    knowledge_demo_probes,
    run_demo_probes,
    validate_collection,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _schema_obj(type_name: str) -> SimpleNamespace:
    return SimpleNamespace(data_type=SimpleNamespace(value=type_name))


def _contract_schema(role: str) -> dict:
    contract = apartments_contract() if role == "apartments" else knowledge_contract("k")
    return {i.field_name: _schema_obj(i.schema_type) for i in contract.payload_indexes}


def _info(
    points: int = 10,
    dense: tuple[str, ...] = ("dense", "colbert"),
    sparse: tuple[str, ...] = ("bm42",),
    payload_schema: dict | None = None,
    dense_size: int = BGEM3_DENSE_DIM,
    role: str = "knowledge",
) -> SimpleNamespace:
    return SimpleNamespace(
        points_count=points,
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={name: SimpleNamespace(size=dense_size) for name in dense},
                sparse_vectors={name: SimpleNamespace() for name in sparse},
            )
        ),
        payload_schema=(payload_schema if payload_schema is not None else _contract_schema(role)),
    )


class FakeQdrant:
    """Minimal AsyncQdrantClient double for read-only validation."""

    def __init__(
        self,
        exists: bool = True,
        info: SimpleNamespace | None = None,
        counts: dict | None = None,
        default_count: int = 1,
    ) -> None:
        self._exists = exists
        self._info = info or _info()
        self._counts = counts or {}
        self._default_count = default_count
        self.count_calls: list = []

    async def collection_exists(self, collection: str) -> bool:
        return self._exists

    async def get_collection(self, collection: str) -> SimpleNamespace:
        if not self._exists:
            raise RuntimeError("collection missing")
        return self._info

    @staticmethod
    def _filter_key(count_filter) -> tuple:
        if count_filter is None:
            return ("none",)
        parts = []
        for cond in count_filter.must or []:
            has_id = getattr(cond, "has_id", None)
            if has_id is not None:
                parts.append(("ids", tuple(sorted(str(i) for i in has_id.has_id))))
                continue
            if getattr(cond, "range", None) is not None:
                parts.append((cond.key, "lte", cond.range.lte))
            else:
                match = cond.match
                any_value = getattr(match, "any", None)
                parts.append((cond.key, tuple(any_value) if any_value else match.value))
        return tuple(parts)

    async def count(self, collection_name: str, count_filter=None, exact: bool = False):
        self.count_calls.append(count_filter)
        key = self._filter_key(count_filter)
        return SimpleNamespace(count=self._counts.get(key, self._default_count))


def _demo_rows() -> list[dict]:
    return [
        {
            "complex_name": "Sample Sea Residence",
            "section": "A",
            "apartment_number": "101",
            "rooms": 2,
            "city": "Бургас",
        },
        {
            "complex_name": "Sample Garden Residence",
            "section": "B",
            "apartment_number": "12",
            "rooms": 1,
            "city": "Варна",
        },
    ]


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class TestContractShapes:
    """Explicit contracts pin the schema both product collections need."""

    def test_knowledge_contract_targets_configured_collection(self):
        contract = knowledge_contract("gdrive_documents_bge_scalar")
        assert contract.role == "knowledge"
        assert contract.collection_name == "gdrive_documents_bge_scalar"
        assert contract.min_points == 1

    def test_knowledge_dense_vectors_pin_bge_m3_dimension(self):
        contract = knowledge_contract("k")
        by_name = {v.name: v for v in contract.dense_vectors}
        assert by_name["dense"].size == 1024
        assert by_name["dense"].required is True
        # colbert degrades to RRF fallback — advisory, not required.
        assert by_name["colbert"].required is False
        assert by_name["colbert"].size == 1024

    def test_knowledge_sparse_and_payload_indexes(self):
        contract = knowledge_contract("k")
        assert [v.name for v in contract.sparse_vectors] == ["bm42"]
        fields = {i.field_name: i.schema_type for i in contract.payload_indexes}
        assert fields["file_id"] == "keyword"
        assert fields["metadata.doc_id"] == "keyword"
        assert fields["metadata.order"] == "integer"
        assert fields["metadata.chunk_id"] == "integer"

    def test_apartments_contract_pins_hardcoded_collection(self):
        contract = apartments_contract()
        assert contract.collection_name == APARTMENTS_COLLECTION
        assert contract.role == "apartments"
        fields = {i.field_name: i.schema_type for i in contract.payload_indexes}
        assert fields["city"] == "keyword"
        assert fields["rooms"] == "integer"
        assert fields["price_eur"] == "float"
        assert fields["is_furnished"] == "bool"

    def test_with_collection_name_keeps_contract(self):
        contract = apartments_contract().with_collection_name("i3202-apartments")
        assert contract.collection_name == "i3202-apartments"
        assert contract.payload_indexes == apartments_contract().payload_indexes


# ---------------------------------------------------------------------------
# validate_collection
# ---------------------------------------------------------------------------


class TestValidateCollection:
    """Missing, empty, and incompatible collections are distinct failures."""

    async def test_missing_collection_is_actionable_failure(self):
        readiness = await validate_collection(FakeQdrant(exists=False), knowledge_contract("k"))
        assert readiness.ok is False
        assert [f.kind for f in readiness.failures] == [KIND_MISSING]
        assert "make demo-bootstrap" in readiness.failures[0].remediation
        assert readiness.points_count is None

    async def test_ready_collection_passes(self):
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=278)), knowledge_contract("k")
        )
        assert readiness.ok is True
        assert readiness.failures == []
        assert readiness.points_count == 278

    async def test_empty_collection_is_distinct_from_missing(self):
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=0)), knowledge_contract("k")
        )
        assert readiness.ok is False
        assert readiness.failures[0].kind == KIND_EMPTY
        assert "ingest" in readiness.failures[0].remediation

    async def test_insufficient_points_reported(self):
        contract = knowledge_contract("k")
        custom = type(contract)(
            role=contract.role,
            collection_name=contract.collection_name,
            dense_vectors=contract.dense_vectors,
            sparse_vectors=contract.sparse_vectors,
            payload_indexes=contract.payload_indexes,
            min_points=5,
        )
        readiness = await validate_collection(FakeQdrant(info=_info(points=2)), custom)
        assert readiness.ok is False
        assert readiness.failures[0].kind == KIND_INSUFFICIENT_DATA
        assert "2 points" in readiness.failures[0].message

    async def test_wrong_dense_dimension_is_schema_incompatible(self):
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=5, dense_size=768)), knowledge_contract("k")
        )
        assert readiness.ok is False
        kinds = {f.kind for f in readiness.failures}
        assert KIND_SCHEMA_INCOMPATIBLE in kinds
        failure = next(f for f in readiness.failures if f.kind == KIND_SCHEMA_INCOMPATIBLE)
        assert "768-dimensional" in failure.message
        assert "1024" in failure.message

    async def test_missing_required_dense_fails(self):
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=5, dense=())), knowledge_contract("k")
        )
        assert readiness.ok is False
        assert any("dense" in f.message for f in readiness.failures)

    async def test_missing_sparse_fails(self):
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=5, sparse=())), knowledge_contract("k")
        )
        assert readiness.ok is False
        assert any("bm42" in f.message for f in readiness.failures)

    async def test_missing_advisory_colbert_warns_but_passes(self, caplog):
        with caplog.at_level(logging.WARNING):
            readiness = await validate_collection(
                FakeQdrant(info=_info(points=5, dense=("dense",))), knowledge_contract("k")
            )
        assert readiness.ok is True
        assert "colbert" in caplog.text.lower()

    async def test_missing_payload_index_fails_with_index_remediation(self):
        schema = _contract_schema("knowledge")
        schema.pop("metadata.doc_id")
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=5, payload_schema=schema)), knowledge_contract("k")
        )
        assert readiness.ok is False
        failure = readiness.failures[0]
        assert failure.kind == KIND_SCHEMA_INCOMPATIBLE
        assert "payload index" in failure.message
        assert "metadata.doc_id" in failure.message
        assert "qdrant-ensure-indexes" in failure.remediation

    async def test_wrong_payload_index_type_fails(self):
        schema = _contract_schema("knowledge")
        schema["metadata.order"] = _schema_obj("keyword")
        readiness = await validate_collection(
            FakeQdrant(info=_info(points=5, payload_schema=schema)), knowledge_contract("k")
        )
        assert readiness.ok is False
        assert any("metadata.order" in f.message for f in readiness.failures)

    async def test_non_dict_payload_schema_treated_as_missing(self):
        bare_info = SimpleNamespace(
            points_count=5,
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={"dense": SimpleNamespace(size=1024)},
                    sparse_vectors={"bm42": SimpleNamespace()},
                )
            ),
            payload_schema=None,
        )
        readiness = await validate_collection(FakeQdrant(info=bare_info), knowledge_contract("k"))
        assert readiness.ok is False
        assert any("payload index" in f.message for f in readiness.failures)

    async def test_connectivity_exception_propagates(self):
        client = FakeQdrant(exists=False)

        async def _boom(collection: str) -> bool:
            raise ConnectionError("refused")

        client.collection_exists = _boom
        with pytest.raises(ConnectionError):
            await validate_collection(client, knowledge_contract("k"))


# ---------------------------------------------------------------------------
# Demo probes
# ---------------------------------------------------------------------------


class TestDemoProbes:
    """Probes prove shipped queries against prepared data, no embeddings needed."""

    async def test_matching_probe_passes_and_records_results(self):
        client = FakeQdrant(default_count=2)
        readiness = await validate_collection(
            client,
            knowledge_contract("k"),
            run_probes=True,
            probes=knowledge_demo_probes(),
        )
        assert readiness.ok is True
        assert len(readiness.probe_results) == len(KNOWLEDGE_DEMO_DOC_IDS)
        assert all(count >= 1 for count in readiness.probe_results.values())

    async def test_zero_result_probe_is_probe_mismatch_not_empty(self):
        client = FakeQdrant(default_count=0)
        readiness = await validate_collection(
            client,
            knowledge_contract("k"),
            run_probes=True,
            probes=knowledge_demo_probes(),
        )
        assert readiness.ok is False
        kinds = {f.kind for f in readiness.failures}
        assert KIND_PROBE_MISMATCH in kinds
        assert KIND_EMPTY not in kinds
        failure = next(f for f in readiness.failures if f.kind == KIND_PROBE_MISMATCH)
        assert "advertised query" in failure.message

    async def test_intentional_no_result_probe_passes_on_zero(self):
        probes = apartment_demo_probes(_demo_rows())
        no_result = probes[-1]
        assert no_result.expect_results is False

        client = FakeQdrant(info=_info(role="apartments"), counts={(("price_eur", "lte", 1.0),): 0})
        readiness = await validate_collection(
            client,
            apartments_contract(),
            run_probes=True,
            probes=(no_result,),
        )
        assert readiness.ok is True
        assert readiness.probe_results == {"intentional-no-result": 0}

    async def test_intentional_no_result_probe_fails_on_results(self):
        probes = apartment_demo_probes(_demo_rows())
        client = FakeQdrant(
            info=_info(role="apartments"), default_count=3
        )  # every filter "matches"
        readiness = await validate_collection(
            client,
            apartments_contract(),
            run_probes=True,
            probes=(probes[-1],),
        )
        assert readiness.ok is False
        failure = readiness.failures[0]
        assert failure.kind == KIND_PROBE_MISMATCH
        assert "matched 3 points" in failure.message

    async def test_run_demo_probes_returns_counts(self):
        client = FakeQdrant(default_count=1)
        probes = apartment_demo_probes(_demo_rows())
        counts = await run_demo_probes(client, "apartments", probes)
        assert set(counts) == {p.name for p in probes}
        assert len(client.count_calls) == len(probes)


class TestProbeFilterBuilder:
    """build_probe_filter mirrors the production apartment filter semantics."""

    def test_empty_filters_return_none(self):
        assert build_probe_filter({}) is None

    def test_exact_match_uses_match_value(self):
        f = build_probe_filter({"city": "Бургас"})
        cond = f.must[0]
        assert cond.key == "city"
        assert isinstance(cond.match, MatchValue)
        assert cond.match.value == "Бургас"

    def test_range_dict_uses_range(self):
        f = build_probe_filter({"price_eur": {"gte": 1000, "lte": 200000}})
        cond = f.must[0]
        assert cond.key == "price_eur"
        assert isinstance(cond.range, Range)
        assert cond.range.gte == 1000
        assert cond.range.lte == 200000

    def test_list_uses_match_any(self):
        f = build_probe_filter({"view_tags": ["sea", "pool"]})
        assert isinstance(f.must[0].match, MatchAny)
        assert f.must[0].match.any == ["sea", "pool"]

    def test_bool_uses_match_value(self):
        f = build_probe_filter({"is_furnished": True})
        assert f.must[0].match.value is True


# ---------------------------------------------------------------------------
# Shipped demo fixtures
# ---------------------------------------------------------------------------


class TestShippedDemoFixtures:
    """The shipped demo data drives deterministic, idempotent proofs."""

    def test_knowledge_demo_point_ids_are_deterministic(self):
        assert knowledge_demo_point_id("article_115") == knowledge_demo_point_id("article_115")
        assert len({knowledge_demo_point_id(d) for d in KNOWLEDGE_DEMO_DOC_IDS}) == len(
            KNOWLEDGE_DEMO_DOC_IDS
        )

    def test_apartment_demo_point_ids_match_ingestion_flow(self):
        from src.ingestion.apartments.flow import generate_point_id

        assert apartment_demo_point_id("Sample Sea Residence", "A", "101") == generate_point_id(
            "Sample Sea Residence", "A", "101"
        )

    def test_knowledge_probes_start_with_known_corpus_question_source(self):
        probes = knowledge_demo_probes()
        assert probes[0].name == "known-corpus:article_115"
        assert probes[0].filters == {"metadata.id": "article_115"}
        assert all(p.expect_results for p in probes)

    def test_apartment_probes_cover_every_shipped_row(self):
        probes = apartment_demo_probes(_demo_rows())
        row_probes = probes[:-1]
        assert len(row_probes) == len(_demo_rows())
        assert row_probes[0].filters == {"rooms": 2, "city": "Бургас"}
        assert probes[-1].name == "intentional-no-result"
        assert probes[-1].filters == {"price_eur": {"lte": 1}}
