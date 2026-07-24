"""Contract guards for the binary Qdrant collection setup."""

from types import SimpleNamespace
from unittest import mock

from qdrant_client.models import (
    BinaryQuantization,
    Modifier,
    MultiVectorComparator,
    PayloadSchemaType,
)

from scripts._qdrant_collection_setup import payload_index_types
from scripts.setup_binary_collection import (
    PAYLOAD_INDEX_FIELDS,
    create_binary_collection,
    create_payload_indexes,
    verify_collection_indexes,
)


class TestBinaryCollectionSetup:
    def test_create_collection_uses_binary_quantization_colbert_and_bm42(self) -> None:
        client = mock.MagicMock()

        create_binary_collection(client, "binary-test")

        call = client.create_collection.call_args
        assert call.kwargs["collection_name"] == "binary-test"

        dense = call.kwargs["vectors_config"]["dense"]
        assert isinstance(dense.quantization_config, BinaryQuantization)
        assert dense.quantization_config.binary.always_ram is True
        colbert = call.kwargs["vectors_config"]["colbert"]
        assert colbert.size == 1024
        assert colbert.multivector_config.comparator is MultiVectorComparator.MAX_SIM
        assert colbert.hnsw_config.m == 0

        bm42 = call.kwargs["sparse_vectors_config"]["bm42"]
        assert bm42.modifier is Modifier.IDF

    def test_create_payload_indexes_all_required_keyword_fields(self) -> None:
        client = mock.MagicMock()

        create_payload_indexes(client, "binary-test")

        keyword_fields = {
            call.kwargs["field_name"]
            for call in client.create_payload_index.call_args_list
            if call.kwargs["field_schema"] is PayloadSchemaType.KEYWORD
        }
        assert keyword_fields == {
            "file_id",
            "metadata.file_id",
            "metadata.doc_id",
            "metadata.source",
            "metadata.document_name",
            "metadata.article_number",
            "metadata.city",
            "metadata.source_type",
            "metadata.topic",
            "metadata.doc_type",
            "metadata.jurisdiction",
            "metadata.audience",
            "metadata.language",
        }

    def test_verify_indexes_uses_all_payload_fields_and_types(self) -> None:
        required_indexes = payload_index_types(PAYLOAD_INDEX_FIELDS)
        client = mock.MagicMock()
        client.get_collection.return_value = SimpleNamespace(
            payload_schema={
                field: SimpleNamespace(data_type=index_type)
                for field, index_type in required_indexes.items()
                if field != "metadata.jurisdiction"
            }
        )

        assert verify_collection_indexes(client, "binary-test") == ["metadata.jurisdiction"]
