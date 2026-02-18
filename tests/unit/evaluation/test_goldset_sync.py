"""Tests for gold set sync to Langfuse dataset."""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.eval.goldset_sync import load_ground_truth, sync_to_langfuse


def test_load_ground_truth_returns_samples():
    samples = load_ground_truth("tests/eval/ground_truth.json")
    assert len(samples) == 55
    assert "question" in samples[0]
    assert "ground_truth" in samples[0]


def test_sync_creates_dataset_when_not_exists():
    mock_langfuse = MagicMock()
    mock_dataset = MagicMock()
    mock_langfuse.get_dataset.side_effect = Exception("not found")
    mock_langfuse.create_dataset.return_value = mock_dataset

    samples = [
        {
            "id": 1,
            "question": "Q1",
            "ground_truth": "A1",
            "category": "test",
            "difficulty": "easy",
        }
    ]
    count = sync_to_langfuse(mock_langfuse, "test-dataset", samples)

    mock_langfuse.create_dataset.assert_called_once_with(name="test-dataset")
    mock_langfuse.create_dataset_item.assert_called_once()
    assert count == 1


def test_sync_uses_existing_dataset():
    mock_langfuse = MagicMock()
    mock_dataset = MagicMock()
    mock_langfuse.get_dataset.return_value = mock_dataset

    samples = [
        {"id": 1, "question": "Q1", "ground_truth": "A1", "category": "c", "difficulty": "d"},
        {"id": 2, "question": "Q2", "ground_truth": "A2", "category": "c", "difficulty": "d"},
    ]
    count = sync_to_langfuse(mock_langfuse, "existing-dataset", samples)

    mock_langfuse.create_dataset.assert_not_called()
    assert mock_langfuse.create_dataset_item.call_count == 2
    assert count == 2
