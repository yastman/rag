"""Unit tests for src.runtime.qdrant.contracts — one schema/identity/filter authority (#3333).

The canonical module owns pure data every Qdrant consumer shares: payload-index
maps, the apartment point-id function, the payload filter builder, strict-mode
limits, and the filtered-field registries that parity tests assert against.
"""

from qdrant_client.models import MatchAny, MatchValue, Range

from src.runtime.qdrant import contracts


# ---------------------------------------------------------------------------
# Apartment point identity
# ---------------------------------------------------------------------------


class TestApartmentPointIdentity:
    """One deterministic apartment point-id function for ingestion and readiness."""

    def test_pinned_deterministic_value(self):
        # Characterization value of the pre-#3333 duplicated implementation —
        # the canonical function must reproduce it exactly (populated data!).
        assert (
            contracts.apartment_point_id("Sample Sea Residence", "A", "101")
            == "5b3e0a80-6eb3-53c8-9754-c329a01148e3"
        )

    def test_distinct_rows_get_distinct_ids(self):
        ids = {
            contracts.apartment_point_id("Sample Sea Residence", "A", "101"),
            contracts.apartment_point_id("Sample Sea Residence", "A", "102"),
            contracts.apartment_point_id("Sample Garden Residence", "B", "12"),
        }
        assert len(ids) == 3

    def test_ingestion_flow_uses_the_canonical_function(self):
        from src.ingestion.apartments import flow

        assert flow.apartment_point_id is contracts.apartment_point_id


# ---------------------------------------------------------------------------
# Payload filter builder
# ---------------------------------------------------------------------------


class TestBuildPayloadFilter:
    """One filter builder for production search and readiness probes."""

    def test_none_and_empty_return_none(self):
        assert contracts.build_payload_filter(None) is None
        assert contracts.build_payload_filter({}) is None

    def test_exact_match_uses_match_value(self):
        f = contracts.build_payload_filter({"city": "Бургас"})
        assert f is not None
        cond = f.must[0]
        assert cond.key == "city"
        assert isinstance(cond.match, MatchValue)
        assert cond.match.value == "Бургас"

    def test_range_dict_uses_range(self):
        f = contracts.build_payload_filter({"price_eur": {"gte": 1000, "lte": 200000}})
        cond = f.must[0]
        assert cond.key == "price_eur"
        assert isinstance(cond.range, Range)
        assert cond.range.gte == 1000
        assert cond.range.lte == 200000

    def test_list_uses_match_any(self):
        f = contracts.build_payload_filter({"view_tags": ["sea", "pool"]})
        assert isinstance(f.must[0].match, MatchAny)
        assert f.must[0].match.any == ["sea", "pool"]

    def test_bool_uses_match_value_not_range(self):
        f = contracts.build_payload_filter({"is_furnished": True})
        assert f.must[0].match.value is True
        assert f.must[0].range is None


# ---------------------------------------------------------------------------
# Canonical payload-index maps
# ---------------------------------------------------------------------------


class TestCanonicalIndexMaps:
    """The canonical maps are the one schema authority for both collections."""

    def test_knowledge_map_declares_the_canonical_identifier(self):
        flat = dict(contracts.flat_payload_indexes(contracts.KNOWLEDGE_PAYLOAD_INDEXES))
        assert flat["metadata.doc_id"] == "keyword"

    def test_knowledge_map_covers_bootstrap_keyword_fields(self):
        flat = dict(contracts.flat_payload_indexes(contracts.KNOWLEDGE_PAYLOAD_INDEXES))
        for field in (
            "file_id",
            "metadata.file_id",
            "metadata.doc_id",
            "metadata.source",
            "metadata.file_name",
            "metadata.mime_type",
            "metadata.source_type",
            "metadata.topic",
            "metadata.doc_type",
            "metadata.jurisdiction",
            "metadata.audience",
            "metadata.language",
        ):
            assert flat[field] == "keyword", field
        assert flat["metadata.order"] == "integer"
        assert flat["metadata.chunk_id"] == "integer"

    def test_apartments_map_pins_advertised_query_fields(self):
        flat = dict(contracts.flat_payload_indexes(contracts.APARTMENTS_PAYLOAD_INDEXES))
        assert flat["city"] == "keyword"
        assert flat["rooms"] == "integer"
        assert flat["price_eur"] == "float"
        assert flat["is_furnished"] == "bool"


# ---------------------------------------------------------------------------
# Filter-field / index parity (the negative-parity harness)
# ---------------------------------------------------------------------------


class TestFilterIndexParity:
    """Every filtered field must have a declared index — losing one fails."""

    def test_apartment_filtered_fields_all_have_indexes(self):
        missing = contracts.missing_filter_indexes(
            contracts.APARTMENT_FILTER_FIELDS,
            contracts.APARTMENTS_PAYLOAD_INDEXES,
        )
        assert missing == ()

    def test_knowledge_filtered_fields_all_have_indexes(self):
        missing = contracts.missing_filter_indexes(
            contracts.KNOWLEDGE_FILTER_FIELDS,
            contracts.KNOWLEDGE_PAYLOAD_INDEXES,
        )
        assert missing == ()

    def test_parity_breaks_when_a_filtered_field_loses_its_index(self):
        reduced = tuple(
            (schema, tuple(f for f in fields if f != "city"))
            for schema, fields in contracts.APARTMENTS_PAYLOAD_INDEXES
        )
        missing = contracts.missing_filter_indexes(
            contracts.APARTMENT_FILTER_FIELDS,
            reduced,
        )
        assert missing == ("city",)

    def test_apartment_filter_registry_covers_product_and_probe_fields(self):
        # Fields extracted by the production filter path (HardFilters) and the
        # demo probes — dropping any from the index map must fail the parity
        # tests above. apartment_number/view_primary are identity/display
        # payload, never filtered, so they stay out of this registry.
        assert set(contracts.APARTMENT_FILTER_FIELDS) == {
            "city",
            "complex_name",
            "rooms",
            "price_eur",
            "area_m2",
            "floor",
            "section",
            "view_tags",
            "is_furnished",
            "is_promotion",
        }


# ---------------------------------------------------------------------------
# Strict-mode guardrails (applied by explicit bootstrap, never by reads)
# ---------------------------------------------------------------------------


class TestStrictModeContract:
    def test_strict_mode_config_pins_guardrails(self):
        cfg = contracts.strict_mode_config()
        assert cfg.model_dump(exclude_none=True) == {
            "enabled": True,
            "max_query_limit": 100,
            "max_timeout": 30,
            "search_max_hnsw_ef": 512,
            "search_max_batchsize": 10,
            "max_resident_memory_percent": 80,
        }


# ---------------------------------------------------------------------------
# Consumer parity — other surfaces must derive from the canonical maps
# ---------------------------------------------------------------------------


class TestConsumerParity:
    """Setup and readiness consume the canonical maps (one implementation)."""

    def test_readiness_contracts_use_canonical_index_maps(self):
        from src.runtime.qdrant.readiness import apartments_contract, knowledge_contract

        knowledge = knowledge_contract("k")
        assert tuple(
            (i.field_name, i.schema_type) for i in knowledge.payload_indexes
        ) == contracts.flat_payload_indexes(contracts.KNOWLEDGE_PAYLOAD_INDEXES)

        apartments = apartments_contract()
        assert tuple(
            (i.field_name, i.schema_type) for i in apartments.payload_indexes
        ) == contracts.flat_payload_indexes(contracts.APARTMENTS_PAYLOAD_INDEXES)

    def test_knowledge_demo_probes_filter_the_indexed_identifier(self):
        from src.runtime.qdrant.readiness import knowledge_demo_probes

        probes = knowledge_demo_probes()
        assert probes
        for probe in probes:
            ((field, value),) = probe.filters.items()
            assert field == "metadata.doc_id"
            assert value

    def test_setup_script_field_maps_derive_from_canonical(self):
        from scripts._qdrant_collection_setup import (
            APARTMENT_PAYLOAD_INDEX_FIELDS,
            GDRIVE_PAYLOAD_INDEX_FIELDS,
            payload_index_types,
        )

        assert payload_index_types(GDRIVE_PAYLOAD_INDEX_FIELDS) == dict(
            contracts.flat_payload_indexes(contracts.KNOWLEDGE_PAYLOAD_INDEXES)
        )
        assert payload_index_types(APARTMENT_PAYLOAD_INDEX_FIELDS) == dict(
            contracts.flat_payload_indexes(contracts.APARTMENTS_PAYLOAD_INDEXES)
        )

    def test_bootstrap_uses_canonical_vector_dimension(self):
        # commands.py bootstrap and demo_bootstrap must not hardcode 1024.
        import inspect

        import scripts.demo_bootstrap as db
        from src.ingestion.unified import commands

        for func in (commands.cmd_bootstrap, db.create_knowledge_collection_schema):
            source = inspect.getsource(func)
            assert "1024" not in source, f"{func.__name__} hardcodes the dense dimension"
