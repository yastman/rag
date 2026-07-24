"""Regression guard: setup_collection.py must use models.PayloadSchemaType.BOOL for is_furnished."""

import subprocess
import sys
from pathlib import Path
from unittest import mock

from qdrant_client import models


APARTMENT_INDEX_ORACLE = {
    "complex_name": models.PayloadSchemaType.KEYWORD,
    "city": models.PayloadSchemaType.KEYWORD,
    "section": models.PayloadSchemaType.KEYWORD,
    "apartment_number": models.PayloadSchemaType.KEYWORD,
    "view_primary": models.PayloadSchemaType.KEYWORD,
    "view_tags": models.PayloadSchemaType.KEYWORD,
    "rooms": models.PayloadSchemaType.INTEGER,
    "floor": models.PayloadSchemaType.INTEGER,
    "price_eur": models.PayloadSchemaType.FLOAT,
    "area_m2": models.PayloadSchemaType.FLOAT,
    "is_furnished": models.PayloadSchemaType.BOOL,
    "is_promotion": models.PayloadSchemaType.BOOL,
}


def test_apartment_setup_uses_the_literal_top_level_payload_oracle() -> None:
    """The real apartment payload's field names and types are indexed unchanged."""
    from scripts.apartments.setup_collection import create_payload_indexes

    client = mock.MagicMock()
    create_payload_indexes(client)

    actual = {
        call.kwargs["field_name"]: call.kwargs["field_schema"]
        for call in client.create_payload_index.call_args_list
    }
    assert actual == APARTMENT_INDEX_ORACLE


def test_apartment_setup_module_help_requires_no_qdrant() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.apartments.setup_collection", "--help"],
        cwd=Path(__file__).parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Create apartments Qdrant collection" in result.stdout
