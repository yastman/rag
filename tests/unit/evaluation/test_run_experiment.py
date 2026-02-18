"""Tests for experiment runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def test_build_rag_task_returns_callable():
    from scripts.eval.run_experiment import build_rag_task

    mock_graph = MagicMock()
    task = build_rag_task(mock_graph)
    assert callable(task)


def test_build_rag_task_invokes_graph():
    from scripts.eval.run_experiment import build_rag_task

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "response": "Test answer",
            "retrieved_context": [{"content": "Doc 1", "score": 0.9}],
        }
    )

    task = build_rag_task(mock_graph)
    mock_item = MagicMock()
    mock_item.input = {"question": "What is X?"}

    result = task(item=mock_item)

    assert result["answer"] == "Test answer"
    assert "Doc 1" in result["context"]
