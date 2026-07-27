from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ingestion.chunker import Chunk
from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter, WriteStats
from src.services.bge_m3_client import HybridResult


def _config(tmp_path: Path) -> UnifiedConfig:
    return UnifiedConfig(sync_dir=tmp_path, collection_name="not_meetings")


def test_ingests_one_markdown_artifact_with_contextual_embeddings_and_original_payload(
    tmp_path: Path,
) -> None:
    """Meeting ingestion preserves provenance while delegating all embeddings to the writer."""
    artifact = tmp_path / "meeting.md"
    original = "# Decisions\nShip the indexed artifact.\n"
    artifact.write_text(original, encoding="utf-8")
    contextual = "Decisions\nShip the indexed artifact."
    chunks = [
        Chunk(
            text="Ship the indexed artifact.",
            embedding_text=contextual,
            chunk_id=index,
            document_name=str(artifact),
            article_number="meeting",
            order=index,
            extra_metadata={"headings": ["Decisions"], "chunk_order": index},
        )
        for index in range(65)
    ]
    docling = MagicMock()
    docling.chunk_file_sync.return_value = chunks
    docling.to_ingestion_chunks.side_effect = lambda values, _source, _source_type: values
    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = WriteStats(points_upserted=65)
    writer.client.scroll.return_value = ([], None)
    writer.client.count.return_value = MagicMock(count=65)

    from src.ingestion.unified.flow import ingest_meeting_artifact

    first = ingest_meeting_artifact(artifact, _config(tmp_path), writer, docling)
    result = ingest_meeting_artifact(artifact, _config(tmp_path), writer, docling)

    assert result.processed == 1
    assert result.errors == 0
    assert result.points_upserted == 65
    assert result.exact_points == 65
    assert first == result
    assert artifact.read_text(encoding="utf-8") == original
    assert docling.chunk_file_sync.call_count == 2
    assert writer.upsert_chunks_sync.call_count == 2
    assert (
        writer.upsert_chunks_sync.call_args_list[0].kwargs["file_id"]
        == (writer.upsert_chunks_sync.call_args_list[1].kwargs["file_id"])
    )
    kwargs = writer.upsert_chunks_sync.call_args.kwargs
    assert kwargs["collection_name"] == "meeting_artifacts"
    assert kwargs["source_path"] == str(artifact)
    assert kwargs["file_metadata"]["source_id"]
    assert kwargs["file_metadata"]["source_path"] == str(artifact)
    assert kwargs["file_metadata"]["original_text"] == artifact.read_bytes().decode("utf-8")
    assert [chunk.order for chunk in kwargs["chunks"]] == list(range(65))
    assert all(chunk.text == "Ship the indexed artifact." for chunk in kwargs["chunks"])
    assert all(chunk.embedding_text == contextual for chunk in kwargs["chunks"])


@pytest.mark.parametrize("name", ["missing.md", "meeting.txt"])
def test_rejects_missing_or_unsupported_meeting_artifact(tmp_path: Path, name: str) -> None:
    artifact = tmp_path / name
    if artifact.suffix == ".txt":
        artifact.write_text("meeting", encoding="utf-8")

    from src.ingestion.unified.flow import ingest_meeting_artifact

    with pytest.raises(ValueError, match="existing Markdown"):
        ingest_meeting_artifact(artifact, _config(tmp_path), MagicMock(), MagicMock())


@pytest.mark.asyncio
async def test_meeting_ingest_command_reports_exact_count(tmp_path: Path, capsys) -> None:
    artifact = tmp_path / "meeting.md"
    artifact.write_text("# Meeting", encoding="utf-8")

    from src.ingestion.unified.commands import cmd_meeting_ingest
    from src.ingestion.unified.flow import MeetingIngestionResult

    result = MeetingIngestionResult(processed=1, errors=0, points_upserted=2, exact_points=2)

    # The command's dependencies are patched at their flow boundary to avoid services.
    with (
        pytest.MonkeyPatch.context() as monkeypatch,
    ):
        monkeypatch.setattr(
            "src.ingestion.unified.commands.UnifiedConfig", lambda: _config(tmp_path)
        )
        monkeypatch.setattr("src.ingestion.unified.commands._build_writer", MagicMock())
        monkeypatch.setattr("src.ingestion.unified.commands._make_docling", MagicMock())
        monkeypatch.setattr(
            "src.ingestion.unified.commands.ingest_meeting_artifact", MagicMock(return_value=result)
        )
        assert await cmd_meeting_ingest(type("Args", (), {"artifact": artifact})()) == 0

    assert "processed=1 errors=0 exact_points=2" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_meeting_ingest_fails_when_exact_point_count_is_zero(tmp_path: Path) -> None:
    artifact = tmp_path / "meeting.md"
    artifact.write_text("# Meeting", encoding="utf-8")

    from src.ingestion.unified.commands import cmd_meeting_ingest
    from src.ingestion.unified.flow import MeetingIngestionResult

    result = MeetingIngestionResult(processed=1, errors=0, points_upserted=2, exact_points=0)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "src.ingestion.unified.commands.UnifiedConfig", lambda: _config(tmp_path)
        )
        monkeypatch.setattr("src.ingestion.unified.commands._build_writer", MagicMock())
        monkeypatch.setattr("src.ingestion.unified.commands._make_docling", MagicMock())
        monkeypatch.setattr(
            "src.ingestion.unified.commands.ingest_meeting_artifact", MagicMock(return_value=result)
        )
        assert await cmd_meeting_ingest(type("Args", (), {"artifact": artifact})()) == 1


def test_meeting_ingestion_uses_one_identity_for_absolute_and_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "meeting.md"
    artifact.write_text("# Meeting", encoding="utf-8")
    docling = MagicMock()
    docling.chunk_file_sync.return_value = [MagicMock()]
    docling.to_ingestion_chunks.side_effect = lambda values, _source, _source_type: values
    writer = MagicMock()
    writer.upsert_chunks_sync.return_value = WriteStats(points_upserted=1)
    writer.client.count.return_value = MagicMock(count=1)

    from src.ingestion.unified.flow import ingest_meeting_artifact

    ingest_meeting_artifact(artifact, _config(tmp_path), writer, docling)
    monkeypatch.chdir(tmp_path)
    ingest_meeting_artifact(Path("meeting.md"), _config(tmp_path), writer, docling)

    first, second = writer.upsert_chunks_sync.call_args_list
    assert first.kwargs["file_id"] == second.kwargs["file_id"]
    assert first.kwargs["source_path"] == second.kwargs["source_path"]


@pytest.mark.parametrize(
    ("command_name", "arguments"),
    [
        ("meeting-preflight", ["--artifact", "{artifact}"]),
        ("meeting-ingest", ["--artifact", "{artifact}"]),
        ("meeting-bootstrap", ["--artifact", "{artifact}", "--expected-points", "0"]),
        ("meeting-verify", ["--expected-points", "0"]),
    ],
)
def test_main_dispatches_every_meeting_command(
    tmp_path: Path, command_name: str, arguments: list[str]
) -> None:
    artifact = tmp_path / "meeting.md"
    artifact.write_text("# Meeting", encoding="utf-8")

    from src.ingestion.unified import main as ingestion_main

    handler = f"cmd_{command_name.replace('-', '_')}"
    with pytest.MonkeyPatch.context() as monkeypatch:
        command = AsyncMock(return_value=0)
        monkeypatch.setattr(ingestion_main, handler, command)
        monkeypatch.setattr(
            "sys.argv",
            ["unified", command_name, *[value.format(artifact=artifact) for value in arguments]],
        )
        assert ingestion_main.main() == 0
    command.assert_called_once()


def test_writer_embeds_contextual_text_but_persists_original_meeting_chunk() -> None:
    chunks = [
        Chunk(
            text=f"original {index}",
            chunk_id=index,
            document_name="meeting.md",
            article_number="meeting",
            embedding_text=f"heading{chr(10)}contextual {index}",
            extra_metadata={"headings": ["Heading"], "chunk_order": index},
        )
        for index in range(65)
    ]
    writer = object.__new__(QdrantHybridWriter)
    writer._bge_client = MagicMock()
    writer._bge_client.encode_hybrid.return_value = HybridResult(
        dense_vecs=[[0.1] * 1024 for _ in chunks],
        lexical_weights=[{"indices": [1], "values": [1.0]} for _ in chunks],
        colbert_vecs=[[[0.1] * 1024] for _ in chunks],
    )
    writer._upsert_points_in_batches = MagicMock(return_value=len(chunks))
    writer._delete_stale_points_sync = MagicMock(return_value=0)

    stats = writer.upsert_chunks_sync(
        chunks=chunks,
        file_id="source-id",
        source_path="meeting.md",
        file_metadata={"meeting_artifact": True, "source_id": "source-id"},
        collection_name="meeting_artifacts",
    )

    assert stats.points_upserted == 65
    expected_embeddings = [f"heading{chr(10)}contextual {index}" for index in range(65)]
    assert writer._bge_client.encode_hybrid.call_args_list[0].args == (expected_embeddings,)
    repeated = writer.upsert_chunks_sync(
        chunks=chunks,
        file_id="source-id",
        source_path="meeting.md",
        file_metadata={"meeting_artifact": True, "source_id": "source-id"},
        collection_name="meeting_artifacts",
    )
    assert repeated.points_upserted == 65
    assert writer._bge_client.encode_hybrid.call_args_list[1].args == (expected_embeddings,)
    first_points = writer._upsert_points_in_batches.call_args_list[0].kwargs["points"]
    repeated_points = writer._upsert_points_in_batches.call_args_list[1].kwargs["points"]
    assert [point.id for point in repeated_points] == [point.id for point in first_points]
    points = writer._upsert_points_in_batches.call_args.kwargs["points"]
    assert points[0].payload["page_content"] == "original 0"
    assert points[0].payload["heading"] == "Heading"
    assert points[0].payload["source_id"] == "source-id"
    assert points[-1].payload["chunk_index"] == 64
