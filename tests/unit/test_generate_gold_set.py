"""Tests for gold set generator."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_point(file_id: str, order: int, text: str, source: str = "doc.md") -> SimpleNamespace:
    """Create a mock Qdrant point with payload."""
    return SimpleNamespace(
        payload={
            "page_content": text,
            "metadata": {
                "file_id": file_id,
                "order": order,
                "source": source,
                "chunk_location": f"seq_{order}",
                "file_name": source,
                "section": "",
            },
        },
    )


class TestScrollCollection:
    async def test_returns_all_points(self):
        from scripts.generate_gold_set import scroll_collection

        mock_client = AsyncMock()
        mock_client.scroll.return_value = (
            [_make_point("f1", 0, "text1"), _make_point("f1", 1, "text2")],
            None,
        )
        points = await scroll_collection(mock_client, "test_col")
        assert len(points) == 2

    async def test_pagination(self):
        from scripts.generate_gold_set import scroll_collection

        mock_client = AsyncMock()
        mock_client.scroll.side_effect = [
            ([_make_point("f1", 0, "t1")], "offset2"),
            ([_make_point("f1", 1, "t2")], None),
        ]
        points = await scroll_collection(mock_client, "test_col", batch_size=1)
        assert len(points) == 2
        assert mock_client.scroll.call_count == 2


class TestGroupByDocument:
    def test_groups_and_sorts(self):
        from scripts.generate_gold_set import group_by_document

        points = [
            _make_point("f1", 2, "C"),
            _make_point("f1", 0, "A"),
            _make_point("f2", 0, "X"),
            _make_point("f1", 1, "B"),
        ]
        docs = group_by_document(points)
        assert len(docs) == 2
        assert [c["text"] for c in docs["f1"]["chunks"]] == ["A", "B", "C"]

    def test_single_document(self):
        from scripts.generate_gold_set import group_by_document

        points = [_make_point("f1", 0, "only")]
        docs = group_by_document(points)
        assert len(docs) == 1
        assert docs["f1"]["chunks"][0]["text"] == "only"


class TestCalculateQuestionsCount:
    @pytest.mark.parametrize(
        ("chunks", "expected_min"),
        [(1, 3), (6, 3), (12, 3), (20, 5), (44, 11), (82, 20)],
    )
    def test_formula_min_3(self, chunks: int, expected_min: int):
        from scripts.generate_gold_set import calculate_questions_count

        result = calculate_questions_count(chunks)
        assert result >= 3
        assert result >= expected_min


class TestExportToJsonl:
    def test_writes_valid_jsonl(self, tmp_path: Path):
        from scripts.generate_gold_set import export_to_jsonl

        items = [
            {
                "query": "Вопрос?",
                "answer": "Ответ",
                "source_doc": "doc.md",
                "source_file_id": "f1",
                "source_chunks": ["seq_0"],
                "difficulty": "easy",
                "type": "factual",
            },
        ]
        out = tmp_path / "gold.jsonl"
        export_to_jsonl(out, items)

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["input"]["query"] == "Вопрос?"
        assert data["expected_output"]["answer"] == "Ответ"
        assert data["metadata"]["source_chunks"] == ["seq_0"]

    def test_multiple_items(self, tmp_path: Path):
        from scripts.generate_gold_set import export_to_jsonl

        items = [
            {
                "query": f"q{i}",
                "answer": f"a{i}",
                "source_doc": "d",
                "source_file_id": "f",
                "source_chunks": [],
                "difficulty": "easy",
                "type": "factual",
            }
            for i in range(3)
        ]
        out = tmp_path / "gold.jsonl"
        export_to_jsonl(out, items)
        assert len(out.read_text().strip().split("\n")) == 3


class TestUploadToLangfuse:
    def test_creates_dataset_and_items(self):
        from scripts.generate_gold_set import upload_to_langfuse

        mock_lf = MagicMock()
        mock_lf.get_dataset.side_effect = Exception("not found")
        items = [
            {
                "query": "q?",
                "answer": "a",
                "source_doc": "d",
                "source_file_id": "f1",
                "source_chunks": ["seq_0"],
                "difficulty": "easy",
                "type": "factual",
            },
        ]
        count = upload_to_langfuse(mock_lf, "test-ds", items)
        assert count == 1
        mock_lf.create_dataset.assert_called_once_with(name="test-ds")
        mock_lf.create_dataset_item.assert_called_once()

    def test_reuses_existing_dataset(self):
        from scripts.generate_gold_set import upload_to_langfuse

        mock_lf = MagicMock()
        mock_lf.get_dataset.return_value = MagicMock()  # dataset exists
        items = [
            {
                "query": "q?",
                "answer": "a",
                "source_doc": "d",
                "source_file_id": "f1",
                "source_chunks": ["seq_0"],
                "difficulty": "easy",
                "type": "factual",
            },
        ]
        count = upload_to_langfuse(mock_lf, "test-ds", items)
        assert count == 1
        mock_lf.create_dataset.assert_not_called()

    def test_empty_items(self):
        from scripts.generate_gold_set import upload_to_langfuse

        mock_lf = MagicMock()
        count = upload_to_langfuse(mock_lf, "test-ds", [])
        assert count == 0


class TestAssembleDocumentText:
    def test_joins_chunks(self):
        from scripts.generate_gold_set import assemble_document_text

        doc = {"chunks": [{"text": "A"}, {"text": "B"}, {"text": "C"}]}
        result = assemble_document_text(doc)
        assert result == "A\n\nB\n\nC"
