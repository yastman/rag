"""Tests for scripts/index_services.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.index_services import build_service_chunks, index_services, load_services


def _write_services_yaml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "services.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_services_skips_entries_without_card_text(tmp_path: Path) -> None:
    services_path = _write_services_yaml(
        tmp_path,
        "services:\n"
        "  one:\n"
        "    title: One\n"
        "    card_text: First\n"
        "  two:\n"
        "    title: Two\n"
        "  three:\n"
        "    title: Three\n"
        "    card_text: '   '\n",
    )

    services = load_services(services_path)

    assert services == [("one", {"title": "One", "card_text": "First"})]


def test_build_service_chunks_includes_service_key_in_chunk_metadata(tmp_path: Path) -> None:
    services_path = _write_services_yaml(
        tmp_path,
        "services:\n"
        "  residence:\n"
        "    title: Residence\n"
        "    card_text: Support for residence permits.\n",
    )

    chunks = build_service_chunks(services_path)

    service_key, chunk = chunks[0]
    assert service_key == "residence"
    assert chunk.article_number == "residence"
    assert chunk.document_name == "services.yaml"
    assert chunk.section == "Residence"
    assert chunk.extra_metadata == {"chunk_order": 0, "service_key": "residence"}
    assert chunk.text == "Residence\n\nSupport for residence permits."


def test_index_services_calls_writer_with_writer_contract_metadata(tmp_path: Path) -> None:
    services_path = _write_services_yaml(
        tmp_path,
        "services:\n"
        "  one:\n"
        "    title: One\n"
        "    card_text: First\n"
        "  two:\n"
        "    title: Two\n"
        "    card_text: Second\n",
    )
    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = SimpleNamespace(points_upserted=1, errors=None)

    indexed = index_services(
        writer=writer,
        services_path=services_path,
        collection_name="gdrive_documents_bge",
    )

    assert indexed == 2
    assert writer.upsert_chunks_sync.call_count == 2

    first_call = writer.upsert_chunks_sync.call_args_list[0].kwargs
    second_call = writer.upsert_chunks_sync.call_args_list[1].kwargs

    assert first_call["file_id"] == "services.yaml::one"
    assert second_call["file_id"] == "services.yaml::two"
    assert first_call["source_path"] == str(services_path)
    assert first_call["file_metadata"]["file_name"] == "services.yaml"
    assert first_call["file_metadata"]["mime_type"] == "application/yaml"
    assert first_call["file_metadata"]["service_key"] == "one"
    assert first_call["file_metadata"]["source"] == "services.yaml"


def test_index_services_is_idempotent_for_file_ids(tmp_path: Path) -> None:
    services_path = _write_services_yaml(
        tmp_path,
        "services:\n  mortgage:\n    title: Mortgage\n    card_text: Mortgage consultation.\n",
    )
    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = SimpleNamespace(points_upserted=1, errors=None)

    first_indexed = index_services(
        writer=writer,
        services_path=services_path,
        collection_name="gdrive_documents_bge",
    )
    second_indexed = index_services(
        writer=writer,
        services_path=services_path,
        collection_name="gdrive_documents_bge",
    )

    assert first_indexed == 1
    assert second_indexed == 1
    call_file_ids = [call.kwargs["file_id"] for call in writer.upsert_chunks_sync.call_args_list]
    assert call_file_ids == ["services.yaml::mortgage", "services.yaml::mortgage"]
