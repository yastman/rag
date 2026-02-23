from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import telegram_bot.services.ingestion_cocoindex as cocoindex


@pytest.mark.asyncio
async def test_ingest_from_directory_delegates_to_ingestion_service(monkeypatch) -> None:
    expected = SimpleNamespace(total_documents=1, indexed_nodes=2, duration_seconds=0.2, errors=[])
    delegate = AsyncMock(return_value=expected)
    monkeypatch.setattr(cocoindex, "_ingest_from_directory", delegate)

    result = await cocoindex.ingest_from_directory("/tmp/docs", "unit_collection")

    assert result is expected
    delegate.assert_awaited_once_with("/tmp/docs", "unit_collection")


@pytest.mark.asyncio
async def test_get_ingestion_status_delegates(monkeypatch) -> None:
    expected = {"points": 100, "collection": "documents"}
    delegate = AsyncMock(return_value=expected)
    monkeypatch.setattr(cocoindex, "_get_ingestion_status", delegate)

    result = await cocoindex.get_ingestion_status("documents")

    assert result == expected
    delegate.assert_awaited_once_with("documents")


def test_main_without_args_exits_with_usage(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cocoindex.sys, "argv", ["ingestion_cocoindex"])

    with pytest.raises(SystemExit) as exc:
        cocoindex.main()

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "Usage:" in output
    assert "ingest-dir" in output


def test_main_ingest_dir_without_path_exits(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cocoindex.sys, "argv", ["ingestion_cocoindex", "ingest-dir"])

    with pytest.raises(SystemExit) as exc:
        cocoindex.main()

    assert exc.value.code == 1
    assert "Directory path required" in capsys.readouterr().out


def test_main_unknown_command_exits(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cocoindex.sys, "argv", ["ingestion_cocoindex", "bad-command"])

    with pytest.raises(SystemExit) as exc:
        cocoindex.main()

    assert exc.value.code == 1
    assert "Unknown command: bad-command" in capsys.readouterr().out
