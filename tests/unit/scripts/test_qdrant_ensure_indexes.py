"""Failure contract for the Qdrant index ensure entry point."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from qdrant_client.models import PayloadSchemaType

from scripts._qdrant_collection_setup import create_payload_indexes


def test_shared_index_creator_aggregates_failures() -> None:
    client = MagicMock()
    client.create_payload_index.side_effect = OSError("network unavailable")

    with pytest.raises(RuntimeError, match="city: network unavailable; rooms: network unavailable"):
        create_payload_indexes(
            client,
            "apartments",
            ((PayloadSchemaType.KEYWORD, ("city", "rooms")),),
        )

    assert client.create_payload_index.call_count == 2


from scripts import qdrant_ensure_indexes


def test_ensure_returns_nonzero_when_index_creation_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(qdrant_ensure_indexes, "get_qdrant_client", MagicMock())
    monkeypatch.setattr(
        qdrant_ensure_indexes,
        "ensure_indexes",
        MagicMock(side_effect=OSError("network unavailable")),
    )

    assert qdrant_ensure_indexes.main([]) == 1
    assert "network unavailable" in capsys.readouterr().err


def test_ensure_module_entrypoint_returns_nonzero_when_qdrant_is_unreachable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.qdrant_ensure_indexes"],
        cwd=Path(__file__).parents[3],
        env=os.environ | {"QDRANT_URL": "http://127.0.0.1:1"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "could not ensure indexes" in result.stderr


# ---------------------------------------------------------------------------
# Role-aware index contracts (#3202) — one script, both product collections
# ---------------------------------------------------------------------------


def _created_fields(client: MagicMock, collection: str) -> dict[str, str]:
    """Map field_name -> schema_type for one collection from the mock calls."""
    fields: dict[str, str] = {}
    for call in client.create_payload_index.call_args_list:
        if call.kwargs.get("collection_name") != collection:
            continue
        fields[call.kwargs["field_name"]] = call.kwargs["field_schema"].value
    return fields


def test_role_functions_apply_their_own_field_sets() -> None:
    """Knowledge and apartments roles reuse their shared contracts, no duplication."""
    from scripts._qdrant_collection_setup import (
        APARTMENT_PAYLOAD_INDEX_FIELDS,
        GDRIVE_PAYLOAD_INDEX_FIELDS,
        payload_index_types,
    )

    client = MagicMock()
    qdrant_ensure_indexes.ensure_knowledge_indexes(client, "knowledge_col")
    qdrant_ensure_indexes.ensure_apartments_indexes(client, "apartments_col")

    knowledge_fields = _created_fields(client, "knowledge_col")
    apartments_fields = _created_fields(client, "apartments_col")

    assert knowledge_fields == payload_index_types(GDRIVE_PAYLOAD_INDEX_FIELDS)
    assert apartments_fields == payload_index_types(APARTMENT_PAYLOAD_INDEX_FIELDS)
    # The remediation-critical fields the readiness gate checks are covered.
    assert knowledge_fields["metadata.doc_id"] == "keyword"
    assert apartments_fields["price_eur"] == "float"
    assert apartments_fields["city"] == "keyword"


def test_main_ensures_both_roles_by_default(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(qdrant_ensure_indexes, "get_qdrant_client", MagicMock(return_value=client))
    ensure_k = MagicMock()
    ensure_a = MagicMock()
    monkeypatch.setattr(qdrant_ensure_indexes, "ensure_knowledge_indexes", ensure_k)
    monkeypatch.setattr(qdrant_ensure_indexes, "ensure_apartments_indexes", ensure_a)

    assert qdrant_ensure_indexes.main([]) == 0
    ensure_k.assert_called_once_with(client, "gdrive_documents_bge")
    ensure_a.assert_called_once_with(client, "apartments")


def test_main_respects_collection_overrides(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(qdrant_ensure_indexes, "get_qdrant_client", MagicMock(return_value=client))
    ensure_k = MagicMock()
    ensure_a = MagicMock()
    monkeypatch.setattr(qdrant_ensure_indexes, "ensure_knowledge_indexes", ensure_k)
    monkeypatch.setattr(qdrant_ensure_indexes, "ensure_apartments_indexes", ensure_a)

    argv = ["--collection", "my_knowledge_binary", "--apartments-collection", "my_apartments"]
    assert qdrant_ensure_indexes.main(argv) == 0
    ensure_k.assert_called_once_with(client, "my_knowledge_binary")
    ensure_a.assert_called_once_with(client, "my_apartments")


def test_main_only_flag_restricts_role(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(qdrant_ensure_indexes, "get_qdrant_client", MagicMock(return_value=client))
    ensure_k = MagicMock()
    ensure_a = MagicMock()
    monkeypatch.setattr(qdrant_ensure_indexes, "ensure_knowledge_indexes", ensure_k)
    monkeypatch.setattr(qdrant_ensure_indexes, "ensure_apartments_indexes", ensure_a)

    assert qdrant_ensure_indexes.main(["--only", "apartments"]) == 0
    ensure_k.assert_not_called()
    ensure_a.assert_called_once_with(client, "apartments")
