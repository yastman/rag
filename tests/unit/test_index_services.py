"""Tests for scripts/index_services.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.index_services import build_service_chunks, index_services, load_services


def test_load_services_returns_five_cards() -> None:
    services = load_services(Path("telegram_bot/config/services.yaml"))

    assert len(services) == 5


def test_build_service_chunks_includes_service_key_and_card_text() -> None:
    chunks = build_service_chunks(Path("telegram_bot/config/services.yaml"))

    service_key, chunk = chunks[0]
    assert service_key
    assert service_key in chunk.article_number
    assert chunk.text
    assert chunk.extra_metadata["service_key"] == service_key


def test_build_service_chunks_are_deterministic_for_services_yaml(tmp_path: Path) -> None:
    services_path = tmp_path / "services.yaml"
    services_path.write_text(
        "services:\n"
        "  residence:\n"
        "    title: Residence\n"
        "    card_text: Support for residence permits.\n",
        encoding="utf-8",
    )

    first = build_service_chunks(services_path)
    second = build_service_chunks(services_path)

    assert first[0][0] == "residence"
    assert second[0][0] == "residence"
    assert first[0][1].text == second[0][1].text
    assert first[0][1].document_name == "services.yaml"


def test_index_services_calls_writer_per_service(tmp_path: Path) -> None:
    services_path = tmp_path / "services.yaml"
    services_path.write_text(
        "services:\n"
        "  one:\n"
        "    title: One\n"
        "    card_text: First\n"
        "  two:\n"
        "    title: Two\n"
        "    card_text: Second\n",
        encoding="utf-8",
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


def test_index_services_is_idempotent_for_file_ids(tmp_path: Path) -> None:
    services_path = tmp_path / "services.yaml"
    services_path.write_text(
        "services:\n  mortgage:\n    title: Mortgage\n    card_text: Mortgage consultation.\n",
        encoding="utf-8",
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
