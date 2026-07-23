"""Regression tests for the SDK-native Qdrant payload-index audit."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts import qdrant_audit_indexes
from scripts._qdrant_collection_setup import PAYLOAD_INDEX_FIELDS_BY_COLLECTION, payload_index_types
from scripts.setup_binary_collection import PAYLOAD_INDEX_FIELDS


APARTMENT_INDEX_ORACLE = {
    "complex_name": "keyword",
    "city": "keyword",
    "section": "keyword",
    "apartment_number": "keyword",
    "view_primary": "keyword",
    "view_tags": "keyword",
    "rooms": "integer",
    "floor": "integer",
    "price_eur": "float",
    "area_m2": "float",
    "is_furnished": "bool",
    "is_promotion": "bool",
}


def _client_with_indexes(
    indexed_fields: set[str], indexed_types: dict[str, str] | None = None
) -> MagicMock:
    client = MagicMock()
    client.get_collection.return_value = SimpleNamespace(
        payload_schema={
            field: SimpleNamespace(data_type=(indexed_types or {}).get(field))
            for field in indexed_fields
        }
    )
    return client


def test_audit_selects_gdrive_apartment_and_binary_contracts() -> None:
    assert qdrant_audit_indexes.expected_indexes("gdrive_documents_bge") == set(
        payload_index_types(PAYLOAD_INDEX_FIELDS_BY_COLLECTION["gdrive_documents_bge"])
    )
    assert qdrant_audit_indexes.expected_indexes("apartments") == set(APARTMENT_INDEX_ORACLE)
    assert qdrant_audit_indexes.expected_indexes("gdrive_documents_bge_binary") == set(
        payload_index_types(PAYLOAD_INDEX_FIELDS)
    )


def test_audit_main_uses_the_configured_collection_contract(monkeypatch) -> None:
    collection = "apartments"
    client = _client_with_indexes(set(APARTMENT_INDEX_ORACLE), APARTMENT_INDEX_ORACLE)
    monkeypatch.setattr(qdrant_audit_indexes, "COLLECTION", collection)
    monkeypatch.setattr(qdrant_audit_indexes, "get_qdrant_client", MagicMock(return_value=client))

    assert qdrant_audit_indexes.main() == 0


def test_audit_passes_for_configured_collection_schema(monkeypatch):
    client = _client_with_indexes(qdrant_audit_indexes.EXPECTED_INDEXES)
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(qdrant_audit_indexes, "get_qdrant_client", factory)

    assert qdrant_audit_indexes.main() == 0
    factory.assert_called_once_with(timeout=10, announce=False)
    client.get_collection.assert_called_once_with(qdrant_audit_indexes.COLLECTION)


def test_audit_fails_when_an_apartment_schema_field_is_missing(monkeypatch, capsys):
    missing = "city"
    monkeypatch.setattr(qdrant_audit_indexes, "COLLECTION", "apartments")
    monkeypatch.setattr(
        qdrant_audit_indexes,
        "get_qdrant_client",
        lambda **_kwargs: _client_with_indexes(set(APARTMENT_INDEX_ORACLE) - {missing}),
    )

    assert qdrant_audit_indexes.main() == 1
    assert missing in capsys.readouterr().out


def test_audit_fails_for_an_apartment_field_with_the_wrong_type(monkeypatch, capsys) -> None:
    actual_types = APARTMENT_INDEX_ORACLE | {"price_eur": "integer"}
    monkeypatch.setattr(qdrant_audit_indexes, "COLLECTION", "apartments")
    monkeypatch.setattr(
        qdrant_audit_indexes,
        "get_qdrant_client",
        lambda **_kwargs: _client_with_indexes(set(actual_types), actual_types),
    )

    assert qdrant_audit_indexes.main() == 1
    assert "price_eur: expected float, got integer" in capsys.readouterr().out


def test_audit_reports_client_creation_failure(monkeypatch, capsys):
    """Qdrant SDK client construction failures are reported as audit failures."""
    monkeypatch.setattr(
        qdrant_audit_indexes,
        "get_qdrant_client",
        MagicMock(side_effect=RuntimeError("connection refused")),
    )

    assert qdrant_audit_indexes.main() == 1
    stderr = capsys.readouterr().err
    assert "could not reach Qdrant" in stderr
    assert "connection refused" in stderr


def test_audit_reports_get_collection_failure(monkeypatch, capsys):
    """Qdrant SDK collection lookup failures are reported as audit failures."""
    client = MagicMock()
    client.get_collection.side_effect = RuntimeError("collection unavailable")
    monkeypatch.setattr(
        qdrant_audit_indexes,
        "get_qdrant_client",
        MagicMock(return_value=client),
    )

    assert qdrant_audit_indexes.main() == 1
    assert "collection unavailable" in capsys.readouterr().err


def test_audit_module_entrypoint_reaches_connection_boundary() -> None:
    env = os.environ | {"QDRANT_URL": "http://127.0.0.1:1"}
    result = subprocess.run(
        [sys.executable, "-m", "scripts.qdrant_audit_indexes"],
        cwd=Path(__file__).parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "could not reach Qdrant" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
