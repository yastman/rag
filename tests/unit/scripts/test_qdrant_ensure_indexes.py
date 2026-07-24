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
