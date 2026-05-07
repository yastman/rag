"""Regression guard: setup_collection.py must use models.PayloadSchemaType.BOOL for is_furnished."""

from unittest import mock

from qdrant_client import models


class TestSetupCollectionSchemaTypes:
    """Contract guard: payload indexes must use typed schema constants, not string literals."""

    def test_is_furnished_uses_payload_schema_type_bool(self):
        """is_furnished must be indexed with models.PayloadSchemaType.BOOL, not the string 'bool'."""
        with mock.patch("scripts.apartments.setup_collection.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True  # skip create_collection

            from scripts.apartments.setup_collection import create_payload_indexes

            create_payload_indexes(mock_client)

            calls = mock_client.create_payload_index.call_args_list
            is_furnished_call = None
            for call in calls:
                kwargs = call.kwargs or call[1]
                if kwargs.get("field_name") == "is_furnished":
                    is_furnished_call = kwargs
                    break

            assert is_furnished_call is not None, (
                "create_payload_index was not called for is_furnished"
            )
            assert is_furnished_call["field_schema"] is models.PayloadSchemaType.BOOL, (
                f"expected models.PayloadSchemaType.BOOL, got {is_furnished_call['field_schema']!r}"
            )

    def test_is_promotion_uses_payload_schema_type_bool(self):
        """is_promotion must also be indexed with models.PayloadSchemaType.BOOL."""
        with mock.patch("scripts.apartments.setup_collection.QdrantClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.collection_exists.return_value = True

            from scripts.apartments.setup_collection import create_payload_indexes

            create_payload_indexes(mock_client)

            calls = mock_client.create_payload_index.call_args_list
            is_promotion_call = None
            for call in calls:
                kwargs = call.kwargs or call[1]
                if kwargs.get("field_name") == "is_promotion":
                    is_promotion_call = kwargs
                    break

            assert is_promotion_call is not None, (
                "create_payload_index was not called for is_promotion"
            )
            assert is_promotion_call["field_schema"] is models.PayloadSchemaType.BOOL, (
                f"expected models.PayloadSchemaType.BOOL, got {is_promotion_call['field_schema']!r}"
            )
