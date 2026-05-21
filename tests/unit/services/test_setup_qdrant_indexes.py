"""Regression guard for telegram_bot/setup_qdrant_indexes.py (#1401).

Pins the canonical schema for the document/CSV pipeline:

* ``metadata.furnished`` is created with ``models.PayloadSchemaType.BOOL`` —
  matching what ``src/ingestion/chunker.py`` writes and what
  ``src/ingestion/indexer.py``/``scripts/setup_binary_collection.py`` index.
* The legacy ``metadata.furniture`` ``KEYWORD`` index is *not* created —
  it had zero data hits because the chunker has always written
  ``metadata.furnished`` BOOL.

Mocks ``QdrantClient`` and ``BotConfig`` exactly the way
``tests/unit/scripts/test_apartments_setup_collection.py`` mocks the
apartments collection setup, so no live Qdrant or env is required.
"""

from unittest import mock

from qdrant_client import models


class TestSetupQdrantIndexesFurnishedSchema:
    """Contract guard: document/CSV pipeline canonical = ``metadata.furnished`` BOOL."""

    def test_furnished_index_created_with_bool_schema(self):
        """``metadata.furnished`` must be created with ``PayloadSchemaType.BOOL``."""
        with (
            mock.patch("telegram_bot.setup_qdrant_indexes.QdrantClient") as MockClient,
            mock.patch("telegram_bot.setup_qdrant_indexes.BotConfig") as MockConfig,
        ):
            mock_config = MockConfig.return_value
            mock_config.qdrant_url = "http://localhost:6333"
            mock_config.qdrant_collection = "gdrive_documents_bge"
            mock_config.qdrant_api_key = None

            from telegram_bot.setup_qdrant_indexes import setup_indexes

            setup_indexes()

            mock_client = MockClient.return_value
            calls = mock_client.create_payload_index.call_args_list
            furnished_call = None
            for call in calls:
                kwargs = call.kwargs or call[1]
                if kwargs.get("field_name") == "metadata.furnished":
                    furnished_call = kwargs
                    break

            assert furnished_call is not None, (
                "create_payload_index was not called for metadata.furnished"
            )
            assert furnished_call["field_schema"] is models.PayloadSchemaType.BOOL, (
                f"expected models.PayloadSchemaType.BOOL, got {furnished_call['field_schema']!r}"
            )

    def test_legacy_furniture_index_is_not_created(self):
        """The dead ``metadata.furniture`` keyword index must be retired."""
        with (
            mock.patch("telegram_bot.setup_qdrant_indexes.QdrantClient") as MockClient,
            mock.patch("telegram_bot.setup_qdrant_indexes.BotConfig") as MockConfig,
        ):
            mock_config = MockConfig.return_value
            mock_config.qdrant_url = "http://localhost:6333"
            mock_config.qdrant_collection = "gdrive_documents_bge"
            mock_config.qdrant_api_key = None

            from telegram_bot.setup_qdrant_indexes import setup_indexes

            setup_indexes()

            mock_client = MockClient.return_value
            calls = mock_client.create_payload_index.call_args_list
            field_names = [
                (call.kwargs or call[1]).get("field_name") for call in calls
            ]
            assert "metadata.furniture" not in field_names, (
                f"legacy metadata.furniture index must not be created; got {field_names!r}"
            )
